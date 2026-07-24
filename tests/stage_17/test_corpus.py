"""Stage 17 — corpus round-trip, unit mapping, origin assertion, failed-row exclusion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.optimize.corpus import CorpusRow, Stage17Corpus, load_corpus, save_corpus, to_samples
from aero.optimize.design_space import DesignSpace, DesignVariable
from aero.provenance.four_fold import ProvenanceTuple

pytestmark = pytest.mark.stage_17

_SPACE = DesignSpace(
    variables=(
        DesignVariable(name="max_camber", low=0.0, high=0.08),
        DesignVariable(name="camber_position", low=0.2, high=0.6),
    )
)
_PROV = ProvenanceTuple(
    git_sha="a" * 40,
    dvc_input_hash="b" * 64,
    container_sif_sha256="c" * 64,
    config_hash="d" * 64,
)


def _row(name: str, m: float, p: float, ld: float | None, *, failed: bool = False) -> CorpusRow:
    x = np.asarray([m, p])
    return CorpusRow(
        case_name=name,
        design_named={"max_camber": m, "camber_position": p},
        design_unit=tuple(float(v) for v in _SPACE.to_unit(x)),
        ld=ld,
        failed=failed,
        error="SolverError: diverged" if failed else None,
        provenance=_PROV,
    )


def _corpus(rows: tuple[CorpusRow, ...]) -> Stage17Corpus:
    return Stage17Corpus(
        dataset_id="stage17-naca4-ld",
        space=_SPACE,
        reynolds=5.0e5,
        aoa_deg=4.0,
        end_time=3000.0,
        seed=170,
        n_lhs=2,
        created_at="2026-07-24T00:00:00+00:00",
        rows=rows,
    )


def test_round_trip(tmp_path: Path) -> None:
    corpus = _corpus((_row("a", 0.04, 0.3, 30.0), _row("b", 0.02, 0.5, 25.0)))
    out = tmp_path / "corpus.json"
    save_corpus(corpus, out)
    assert load_corpus(out) == corpus


def test_unit_mapping_consistency() -> None:
    row = _row("a", 0.04, 0.3, 30.0)
    physical = _SPACE.from_unit(np.asarray(row.design_unit))
    assert physical[0] == pytest.approx(0.04)
    assert physical[1] == pytest.approx(0.3)


def test_samples_are_platform_validated_and_unit_featured() -> None:
    corpus = _corpus((_row("a", 0.04, 0.3, 30.0),))
    (sample,) = to_samples(corpus)
    assert sample.data_origin == "platform-validated"
    assert sample.features == corpus.rows[0].design_unit
    assert sample.targets == (30.0,)
    assert sample.case_id == "a"


def test_failed_rows_excluded_from_training() -> None:
    corpus = _corpus((_row("ok", 0.04, 0.3, 30.0), _row("bad", 0.06, 0.4, None, failed=True)))
    samples = to_samples(corpus)
    assert [s.case_id for s in samples] == ["ok"]
    assert len(corpus.rows) == 2  # the failure stays in the bundle as evidence
