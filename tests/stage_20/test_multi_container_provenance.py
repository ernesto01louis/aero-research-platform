"""Stage 20 — the multi-container provenance contract (ADR-038).

A partitioned FSI coupling runs OpenFOAM out of `precice-fsi.sif` and CalculiX out
of `calculix-precice.sif`, so one `container_sif_sha256` cannot describe what ran.
Stage 19 handled that by structurally refusing a *gated* multi-container run;
Stage 20 removes the cause instead, adding a `containers` roster.

The properties that make the change safe rather than merely convenient:

* additive — every pre-Stage-20 tuple, tag set and persisted bundle is unchanged;
* complete — a multi-container run whose roster omits a participant is refused;
* canonical — the roster is name-sorted, so two runs of the same container set
  produce the same record;
* round-trippable — MLflow alone, the repo alone, or the bundle alone each suffice
  to recover the exact SIFs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aero.provenance.four_fold import (
    ContainerRef,
    ProvenanceError,
    ProvenanceTuple,
    container_roster,
)

pytestmark = pytest.mark.stage_20

_FLUID = "c" * 64
_SOLID = "d" * 64


def _tuple(**kwargs: object) -> ProvenanceTuple:
    base: dict[str, object] = {
        "git_sha": "a" * 40,
        "dvc_input_hash": "b" * 64,
        "container_sif_sha256": _FLUID,
        "config_hash": "e" * 64,
    }
    base.update(kwargs)
    return ProvenanceTuple(**base)  # type: ignore[arg-type]


def _roster() -> tuple[ContainerRef, ...]:
    # Name-sorted: "calculix-precice.sif" < "precice-fsi.sif".
    return (
        ContainerRef(name="calculix-precice.sif", sha256=_SOLID),
        ContainerRef(name="precice-fsi.sif", sha256=_FLUID),
    )


class TestBackwardCompatibility:
    def test_a_single_container_tuple_is_unchanged(self) -> None:
        prov = _tuple()
        assert prov.containers == ()
        assert prov.multi_container is False
        assert set(prov.as_mlflow_tags()) == {
            "git_sha",
            "dvc_input_hash",
            "container_sif_sha256",
            "config_hash",
        }

    def test_pre_stage_20_bundle_json_still_parses(self) -> None:
        """Persisted bundles predate the field and must not need migrating."""
        legacy = json.dumps(
            {
                "git_sha": "a" * 40,
                "dvc_input_hash": "b" * 64,
                "container_sif_sha256": _FLUID,
                "config_hash": "e" * 64,
            }
        )
        prov = ProvenanceTuple.model_validate_json(legacy)
        assert prov.containers == ()

    def test_extra_keys_are_still_forbidden(self) -> None:
        """The additive field must not have loosened `extra='forbid'`."""
        with pytest.raises(ValueError):
            _tuple(container_sif_sha256_v2=_SOLID)


class TestRosterCompleteness:
    def test_a_multi_container_tuple_tags_the_full_roster(self) -> None:
        tags = _tuple(containers=_roster()).as_mlflow_tags()
        assert tags["container_sif_set"] == (
            f"calculix-precice.sif={_SOLID},precice-fsi.sif={_FLUID}"
        )
        # The four canonical keys keep their exact shape.
        assert tags["container_sif_sha256"] == _FLUID

    def test_a_one_entry_roster_is_refused(self) -> None:
        """A single-container run wearing multi-container clothes."""
        with pytest.raises(ValueError, match="at least two entries"):
            _tuple(containers=(ContainerRef(name="precice-fsi.sif", sha256=_FLUID),))

    def test_an_unsorted_roster_is_refused(self) -> None:
        """Canonical order, so two runs of the same set compare equal."""
        with pytest.raises(ValueError, match="name-sorted"):
            _tuple(containers=tuple(reversed(_roster())))

    def test_a_duplicated_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="duplicate container names"):
            _tuple(
                containers=(
                    ContainerRef(name="precice-fsi.sif", sha256=_FLUID),
                    ContainerRef(name="precice-fsi.sif", sha256=_SOLID),
                )
            )

    def test_a_roster_omitting_the_container_of_record_is_refused(self) -> None:
        """Otherwise the tuple would describe less than what actually ran."""
        with pytest.raises(ValueError, match="not among the roster"):
            _tuple(
                container_sif_sha256="f" * 64,
                containers=_roster(),
            )


class TestRosterResolution:
    """`container_roster` resolves names through containers/SHA256SUMS."""

    def _repo(self, tmp_path: Path, lines: str) -> Path:
        (tmp_path / "containers").mkdir()
        (tmp_path / "containers" / "SHA256SUMS").write_text(lines, encoding="utf-8")
        return tmp_path

    def test_no_extras_yields_an_empty_roster(self, tmp_path: Path) -> None:
        """A single-container run must not gain a one-entry roster."""
        repo = self._repo(tmp_path, f"{_FLUID}  precice-fsi.sif\n")
        assert (
            container_roster(repo, container_of_record="precice-fsi.sif", extra_container_sifs=())
            == ()
        )

    def test_extras_are_resolved_and_sorted(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path, f"{_FLUID}  precice-fsi.sif\n{_SOLID}  calculix-precice.sif\n")
        roster = container_roster(
            repo,
            container_of_record="precice-fsi.sif",
            extra_container_sifs=("calculix-precice.sif",),
        )
        assert [c.name for c in roster] == ["calculix-precice.sif", "precice-fsi.sif"]
        assert [c.sha256 for c in roster] == [_SOLID, _FLUID]

    def test_an_unrecorded_sif_fails_loud(self, tmp_path: Path) -> None:
        """An unprovenanced container must fail here, as the of-record one always has."""
        repo = self._repo(tmp_path, f"{_FLUID}  precice-fsi.sif\n")
        with pytest.raises(ProvenanceError, match="no SHA256 entry"):
            container_roster(
                repo,
                container_of_record="precice-fsi.sif",
                extra_container_sifs=("calculix-precice.sif",),
            )

    def test_a_repeated_name_fails_loud(self, tmp_path: Path) -> None:
        """A repeat would collapse in the roster and understate what ran."""
        repo = self._repo(tmp_path, f"{_FLUID}  precice-fsi.sif\n")
        with pytest.raises(ProvenanceError, match="more than once"):
            container_roster(
                repo,
                container_of_record="precice-fsi.sif",
                extra_container_sifs=("precice-fsi.sif",),
            )


class TestSpecAgreement:
    """`assert_provenance_describes` is what replaced the blanket gated refusal."""

    def _spec(self, *, sifs: tuple[str, ...]):  # type: ignore[no-untyped-def]
        from aero.adapters.precice import ParticipantSpec, TutorialPin, TutorialSource
        from aero.adapters.precice.case import CoupledCaseSpec

        return CoupledCaseSpec(
            name="hg2007",
            source=TutorialSource(
                pin=TutorialPin(
                    commit="a" * 40, archive_sha256="b" * 64, manifest_path=Path("m.csv")
                ),
                archive_path=Path("a.tar.gz"),
            ),
            max_time=8.0,
            wall_clock_ceiling_s=600,
            analysis_discard_s=4.0,
            participants=tuple(
                ParticipantSpec(name=f"P{i}", workdir=f"w{i}", command="true", sif=s)
                for i, s in enumerate(sifs)
            ),
            container_of_record="precice-fsi.sif",
        )

    def test_a_matching_roster_passes(self) -> None:
        from aero.adapters.precice.case import assert_provenance_describes

        spec = self._spec(sifs=("precice-fsi.sif", "calculix-precice.sif"))
        assert_provenance_describes(spec, _tuple(containers=_roster()))

    def test_a_multi_container_run_with_no_roster_is_refused(self) -> None:
        """The exact hole ADR-038 had to close: two SIFs, one recorded digest."""
        from aero.adapters.precice.case import CoupledCaseError, assert_provenance_describes

        spec = self._spec(sifs=("precice-fsi.sif", "calculix-precice.sif"))
        with pytest.raises(CoupledCaseError, match="missing"):
            assert_provenance_describes(spec, _tuple())

    def test_a_single_container_run_must_not_carry_a_roster(self) -> None:
        from aero.adapters.precice.case import CoupledCaseError, assert_provenance_describes

        spec = self._spec(sifs=("precice-fsi.sif", "precice-fsi.sif"))
        with pytest.raises(CoupledCaseError, match=r"must leave ProvenanceTuple\.containers empty"):
            assert_provenance_describes(spec, _tuple(containers=_roster()))

    def test_a_roster_naming_a_container_the_case_does_not_run_is_refused(self) -> None:
        from aero.adapters.precice.case import CoupledCaseError, assert_provenance_describes

        spec = self._spec(sifs=("precice-fsi.sif", "openfoam-esi.sif"))
        with pytest.raises(CoupledCaseError, match="unexpected"):
            assert_provenance_describes(spec, _tuple(containers=_roster()))


class TestRoundTrip:
    def test_the_tag_alone_recovers_every_sif_and_digest(self) -> None:
        """A reader with only MLflow must be able to invert the record."""
        tag = _tuple(containers=_roster()).container_set_tag()
        recovered = dict(part.split("=", 1) for part in tag.split(","))
        assert recovered == {"calculix-precice.sif": _SOLID, "precice-fsi.sif": _FLUID}

    def test_the_bundle_json_round_trips(self) -> None:
        prov = _tuple(containers=_roster())
        assert ProvenanceTuple.model_validate_json(prov.model_dump_json()) == prov


class TestMlflowTagsCannotBeShadowed:
    def test_extra_tags_may_not_overwrite_a_provenance_tag(self) -> None:
        """MLflow and the Postgres mirror would otherwise describe different runs."""
        import inspect

        from aero.provenance.mlflow import start_provenance_run

        # The guard lives before any mlflow import, so assert on the source rather
        # than importing mlflow (absent without the provenance extra).
        assert "would overwrite provenance tag" in inspect.getsource(start_provenance_run)


class TestPostgresMirror:
    def test_the_insert_carries_the_roster_column(self) -> None:
        from aero.provenance.db import _INSERT_SQL

        assert "container_sif_set" in _INSERT_SQL
        # Six placeholders for six columns — a positional insert that drifts out of
        # step with its column list is a silent data-corruption bug.
        assert _INSERT_SQL.count("%s") == 6

    def test_a_single_container_run_mirrors_null_not_empty_string(self) -> None:
        """ "No roster" and "an empty roster" must stay distinguishable in a query."""
        assert (_tuple().container_set_tag() or None) is None
        assert _tuple(containers=_roster()).container_set_tag()

    def test_the_migration_is_additive(self) -> None:
        """Checked statement by statement, not by substring.

        A raw substring scan trips over the partial index's own
        `WHERE container_sif_set IS NOT NULL` predicate, which is not a column
        constraint at all — so the statements are parsed apart first.
        """
        repo_root = Path(__file__).resolve().parents[2]
        raw = (repo_root / "db/migrations/005_container_set.sql").read_text(encoding="utf-8")
        body = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))
        statements = [s.strip().upper() for s in body.split(";") if s.strip()]
        assert statements, "migration has no statements"

        for stmt in statements:
            assert stmt.startswith(("ALTER TABLE", "CREATE INDEX")), stmt
            for forbidden in ("DROP COLUMN", "ALTER COLUMN", "UPDATE ", "DELETE ", "RENAME"):
                assert forbidden not in stmt, f"{forbidden} in: {stmt}"

        alters = [s for s in statements if s.startswith("ALTER TABLE")]
        assert len(alters) == 1
        assert "ADD COLUMN IF NOT EXISTS CONTAINER_SIF_SET TEXT" in alters[0]
        # Nullable: NULL is what a single-container run records, and every historical
        # row is a single-container run. A NOT NULL column would fail on the ALTER.
        assert "NOT NULL" not in alters[0]
