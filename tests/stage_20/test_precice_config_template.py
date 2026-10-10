"""The authored coupling configuration: a digest-pinned template, rendered and re-read.

An authored case cannot inherit a tutorial's integrity claim, so it has to build one. The
claim this pins is: *the configuration a run executes is the committed template with
exactly the known tokens substituted, and every substituted value is observable in the
parsed model.*

Each test below breaks one link of that chain and requires a loud failure:

- the template's bytes drift from `templates/SHA256SUMS` -> refused on read;
- the template grows a token the renderer does not know, or loses one it fills -> refused
  before substitution, rather than writing a literal `@TOKEN@` into a running case;
- a rendered value does not survive the XML round trip -> `assert_config` refuses;
- the pinned (non-token) coupling numerics drift from what the expectation asserts -> the
  two copies disagree here, in a unit test, instead of in a multi-day campaign.

The last one is what makes the template's digest load-bearing: `max-iterations`, both
convergence limits and every IQN-ILS knob are NOT tokens, so loosening one means editing
digest-pinned bytes whose digest ships in the run's manifest (ADR-036 gate C2's authored
analogue).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from aero.adapters.precice.config import (
    PreciceConfigError,
    assert_config,
    parse_precice_config,
)
from aero.adapters.precice.template import (
    HG2007_TEMPLATE,
    TEMPLATES_DIR,
    PreciceConfigValues,
    hg2007_expectation,
    read_template,
    render_precice_config,
    template_sha256,
    write_precice_config,
)

pytestmark = pytest.mark.stage_20

# The gated operating point's shape (not its final numbers — the deck writer fixes dt from
# the measured-Courant pre-flight, I7). What matters here is that these are floats whose
# repr must survive the round trip exactly.
_VALUES = PreciceConfigValues(
    time_window_size=3.5e-4,
    max_time=1.0145,
    support_radius=0.0018,
    nose_watch_point=(0.0, 0.0),
    te_watch_point=(0.09, 0.0),
    exchange_directory="..",
)


def _rendered(tmp_path: Path):
    return write_precice_config(_VALUES, dest=tmp_path / "precice-config.xml")


class TestTheTemplateIsPinned:
    def test_the_recorded_digest_matches_the_committed_bytes(self) -> None:
        raw = (TEMPLATES_DIR / HG2007_TEMPLATE).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == template_sha256()

    def test_an_edited_template_is_refused_on_read(self, tmp_path: Path, monkeypatch) -> None:
        # Point the module at a scratch copy of templates/ whose template has been edited
        # but whose SHA256SUMS still records the committed digest -- exactly the state a
        # working-tree edit produces.
        scratch = tmp_path / "templates"
        scratch.mkdir()
        (scratch / "SHA256SUMS").write_bytes((TEMPLATES_DIR / "SHA256SUMS").read_bytes())
        edited = (
            (TEMPLATES_DIR / HG2007_TEMPLATE)
            .read_text(encoding="utf-8")
            .replace('value="50"', 'value="500"')
        )
        (scratch / HG2007_TEMPLATE).write_text(edited, encoding="utf-8")
        monkeypatch.setattr("aero.adapters.precice.template.TEMPLATES_DIR", scratch)

        with pytest.raises(PreciceConfigError, match="digest"):
            read_template()

    def test_a_template_with_no_recorded_digest_is_refused(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        scratch = tmp_path / "templates"
        scratch.mkdir()
        (scratch / "SHA256SUMS").write_text("# nothing but a comment\n", encoding="utf-8")
        monkeypatch.setattr("aero.adapters.precice.template.TEMPLATES_DIR", scratch)

        with pytest.raises(PreciceConfigError, match="no template digests"):
            template_sha256()


class TestTheTokenSetIsAsserted:
    def test_an_unknown_token_in_the_template_is_refused(self, tmp_path: Path, monkeypatch) -> None:
        scratch = _scratch_template(
            tmp_path,
            monkeypatch,
            lambda text: text.replace('name="Fluid"', 'name="@PARTICIPANT_NAME@"'),
        )
        assert scratch  # the fixture wrote something

        with pytest.raises(PreciceConfigError, match="PARTICIPANT_NAME"):
            render_precice_config(_VALUES)

    def test_a_missing_token_is_refused(self, tmp_path: Path, monkeypatch) -> None:
        _scratch_template(tmp_path, monkeypatch, lambda text: text.replace("@MAX_TIME@", "5.0"))

        with pytest.raises(PreciceConfigError, match="MAX_TIME"):
            render_precice_config(_VALUES)

    def test_nothing_unsubstituted_survives_a_render(self) -> None:
        assert "@" not in render_precice_config(_VALUES).split("-->", 1)[1]

    def test_both_rbf_blocks_get_the_radius(self) -> None:
        assert render_precice_config(_VALUES).count('support-radius="0.0018"') == 2


class TestTheRenderRoundTrips:
    def test_the_rendered_config_matches_the_expectation_derived_from_the_same_values(
        self, tmp_path: Path
    ) -> None:
        produced = _rendered(tmp_path)
        assert_config(produced, hg2007_expectation(_VALUES))

    def test_the_written_file_carries_its_own_digest(self, tmp_path: Path) -> None:
        produced = _rendered(tmp_path)
        raw = (tmp_path / "precice-config.xml").read_bytes()
        assert produced.source_sha256 == hashlib.sha256(raw).hexdigest()

    def test_every_token_survives_the_round_trip_exactly(self, tmp_path: Path) -> None:
        produced = _rendered(tmp_path)
        scheme = produced.coupling_scheme
        assert scheme.time_window_size == _VALUES.time_window_size
        assert scheme.max_time == _VALUES.max_time
        radii = tuple(m.support_radius for p in produced.participants for m in p.mappings)
        assert radii == (_VALUES.support_radius, _VALUES.support_radius)
        assert produced.watch_point("Solid", "Nose").coordinate == _VALUES.nose_watch_point
        assert produced.watch_point("Solid", "Trailing-Edge").coordinate == _VALUES.te_watch_point
        assert tuple(m.exchange_directory for m in produced.m2n) == (_VALUES.exchange_directory,)

    def test_a_mis_scaled_support_radius_is_caught_by_the_round_trip(self, tmp_path: Path) -> None:
        # Upstream's literal 1. is one metre on a 0.09 m chord. Render it, then assert
        # against the values we MEANT: the round trip is what notices.
        wrong = _VALUES.model_copy(update={"support_radius": 1.0})
        produced = write_precice_config(wrong, dest=tmp_path / "precice-config.xml")
        with pytest.raises(PreciceConfigError, match="mappings"):
            assert_config(produced, hg2007_expectation(_VALUES))

    def test_the_solid_reads_force_not_stress(self, tmp_path: Path) -> None:
        # FSI3's solid reads Stress; the calculix-adapter reads Force. Getting this wrong
        # produces a configuration preCICE accepts and an adapter that never sees a load.
        produced = _rendered(tmp_path)
        assert produced.participant("Solid").read_data == (("Force", "Solid-Mesh"),)

    def test_the_watchpoint_columns_are_predicted_from_the_rendered_mesh_order(
        self, tmp_path: Path
    ) -> None:
        produced = _rendered(tmp_path)
        assert produced.watchpoint_columns("Solid", "Trailing-Edge") == (
            "Time",
            "Coordinate0",
            "Coordinate1",
            "Displacement0",
            "Displacement1",
            "Force0",
            "Force1",
        )


class TestThePinnedNumericsAreWhatTheExpectationAsserts:
    """The template and the expectation state the coupling numerics twice, on purpose.

    The template's copy is what runs; the expectation's copy is what the campaign claims.
    They are only trustworthy together, so a divergence has to fail somewhere — here.
    """

    @pytest.mark.parametrize(
        ("fragment", "why"),
        [
            ('<max-iterations value="50" />', "the iteration cap is not a token"),
            (
                '<relative-convergence-measure limit="5e-3" data="Displacement" '
                'mesh="Solid-Mesh" />',
                "a relative measure on Displacement",
            ),
            (
                '<relative-convergence-measure limit="5e-3" data="Force" mesh="Solid-Mesh" />',
                "a relative measure on Force",
            ),
            ('<filter type="QR2" limit="1e-2" />', "the QR2 filter"),
            ('<initial-relaxation value="0.5" />', "initial relaxation"),
            ('<max-used-iterations value="100" />', "the IQN-ILS window"),
            ('<time-windows-reused value="15" />', "reused time windows"),
        ],
    )
    def test_the_committed_template_carries_the_pinned_numerics(
        self, fragment: str, why: str
    ) -> None:
        assert fragment in read_template(), why

    def test_the_template_declares_no_preconditioner(self, tmp_path: Path) -> None:
        # The expectation asserts ABSENT (None, not UNSET); if the template ever grows one
        # the round trip must refuse rather than silently accept a different acceleration.
        produced = _rendered(tmp_path)
        assert produced.coupling_scheme.acceleration is not None
        assert produced.coupling_scheme.acceleration.preconditioner is None

    def test_a_loosened_convergence_limit_cannot_hide(self) -> None:
        # The edit an impatient operator would make. Even with the digest recomputed to
        # match -- i.e. even if the template edit were "legitimised" -- the expectation
        # still refuses, because the limits are asserted from the module's own constants.
        produced = parse_precice_config(
            render_precice_config(_VALUES).replace('limit="5e-3"', 'limit="5e-1"'),
            source=Path("precice-config.xml"),
            sha256="0" * 64,
        )
        with pytest.raises(PreciceConfigError, match="convergence limits"):
            assert_config(produced, hg2007_expectation(_VALUES))


def _scratch_template(tmp_path: Path, monkeypatch, mutate) -> Path:
    """A scratch templates/ dir holding a mutated template and ITS OWN digest.

    The digest is recomputed so the mutation is not merely caught by the digest check —
    these tests are about the token contract, which must hold on its own.
    """
    scratch = tmp_path / "templates"
    scratch.mkdir(exist_ok=True)
    text = mutate((TEMPLATES_DIR / HG2007_TEMPLATE).read_text(encoding="utf-8"))
    (scratch / HG2007_TEMPLATE).write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    (scratch / "SHA256SUMS").write_text(f"{digest}  {HG2007_TEMPLATE}\n", encoding="utf-8")
    monkeypatch.setattr("aero.adapters.precice.template.TEMPLATES_DIR", scratch)
    return scratch
