"""Importing the committed ``data/vv`` records into a crate payload (ADR-047 D7).

The records were written with default ``model_dump_json()``, which includes computed fields that
``extra='forbid'`` rejects. The legacy import strips those fields guided by the model's
annotations. It then requires the record to be a lossless subset of the model's re-dump: every
stored computed value must recompute bit for bit. Fields added to the schema later must carry
their exact default. Schema drift (the Stage-13 records predate the ``u95_input_basis``
validator) is refused, never "fixed".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aero.crate import CrateError, LegacyRecordError
from aero.crate._canonical import dumps_document
from aero.crate.payload import (
    CRATE_ADDED_FIELDS,
    LEGACY_ADDED_FIELDS,
    load_reportable,
    reportable_document,
)
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import ReportableQuantity

pytestmark = pytest.mark.stage_21

DATA = Path(__file__).resolve().parents[2] / "data" / "vv"
LOADABLE = [
    "stage12_reportable_oscillating_cylinder_lockin",
    "stage15_optimization",
    "stage16_optimization",
    "stage16_relaxed_optimization",
    "stage17_optimization",
]
DRIFTED = [
    "stage13_reportable_plunging_airfoil_hg2007_st02",
    "stage13_reportable_plunging_airfoil_hg2007_st02_lm",
    "stage13_reportable_plunging_airfoil_hg2007_st03",
    "stage13_reportable_plunging_airfoil_hg2007_st03_lm",
]


@pytest.mark.parametrize("record", LOADABLE)
def test_committed_records_import_losslessly_and_round_trip(record: str) -> None:
    raw = (DATA / f"{record}.json").read_bytes()
    result = load_reportable(raw, mode="legacy", what=record)
    doc = dumps_document(reportable_document(result))
    assert load_reportable(doc, mode="crate") == result


@pytest.mark.parametrize("record", DRIFTED)
def test_schema_drift_is_refused_not_migrated(record: str) -> None:
    with pytest.raises(LegacyRecordError, match="u95_input_basis"):
        load_reportable((DATA / f"{record}.json").read_bytes(), mode="legacy", what=record)


def test_crate_mode_refuses_what_legacy_mode_admits() -> None:
    raw = (DATA / "stage17_optimization.json").read_bytes()
    with pytest.raises(CrateError, match="missing from the file"):
        load_reportable(raw, mode="crate")


def test_a_missing_computed_value_is_refused() -> None:
    raw = json.loads((DATA / "stage15_optimization.json").read_bytes())
    del raw["quantities"][0]["u95_total"]
    with pytest.raises(CrateError, match="missing from the file"):
        load_reportable(json.dumps(raw).encode(), mode="legacy")


def test_a_forged_computed_value_is_refused() -> None:
    raw = json.loads((DATA / "stage17_optimization.json").read_bytes())
    raw["optimization"]["improvement"]["required_margin"] = 1.0
    with pytest.raises(CrateError, match="not reproduced"):
        load_reportable(json.dumps(raw).encode(), mode="legacy")


def test_the_added_fields_allowlists_hold_the_real_defaults() -> None:
    assert dict(CRATE_ADDED_FIELDS) == {}  # format v1: a crate's result.json equals its re-dump
    assert LEGACY_ADDED_FIELDS[("provenance", "containers")] == list(
        ProvenanceTuple.model_fields["containers"].default
    )
    assert LEGACY_ADDED_FIELDS[("optimization", "cfd_verified", "containers")] == list(
        ProvenanceTuple.model_fields["containers"].default
    )
    assert (
        LEGACY_ADDED_FIELDS[("quantities", "*", "u95_input_basis")]
        == ReportableQuantity.model_fields["u95_input_basis"].default
    )
