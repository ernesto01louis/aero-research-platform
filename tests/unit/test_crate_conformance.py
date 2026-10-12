"""The RO-Crate 1.3 / Process Run Crate 0.6 / PROV projections conform and agree (ADR-047 D5)."""

from __future__ import annotations

import copy
import json

import pytest
from aero.crate import CrateError, verify_members
from aero.crate.conformance import check_prov_equivalence, check_rocrate
from aero.crate.projections import PRC_PROFILE, RO_CRATE_CONTEXT, RO_CRATE_SPEC

from tests.unit._crate_fixtures import SHAPES, built

pytestmark = pytest.mark.stage_21


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_conforms(shape: str) -> None:
    members = built(shape)
    rocrate = json.loads(members["ro-crate-metadata.json"])
    prov = json.loads(members["prov.json"])
    check_rocrate(rocrate, set(members))
    check_prov_equivalence(rocrate, prov)
    graph = {e["@id"]: e for e in rocrate["@graph"]}
    assert rocrate["@context"][0] == RO_CRATE_CONTEXT
    assert graph["ro-crate-metadata.json"]["conformsTo"] == {"@id": RO_CRATE_SPEC}
    assert {"@id": PRC_PROFILE} in graph["./"]["conformsTo"]
    assert graph["./"]["license"] == {"@id": "https://spdx.org/licenses/CC-BY-4.0"}


def test_every_cited_run_with_a_four_tuple_is_a_create_action_with_its_container() -> None:
    members = built("steady_optimization")
    graph = {e["@id"]: e for e in json.loads(members["ro-crate-metadata.json"])["@graph"]}
    v = verify_members(members)
    run = v.manifest.runs[0]
    action = graph[run.action_id]
    assert "CreateAction" in action["@type"]
    assert graph[action["instrument"]["@id"]]["softwareVersion"] == v.result.provenance.git_sha  # type: ignore[union-attr]
    container = graph[action["containerImage"]["@id"]]
    assert container["sha256"] == v.result.provenance.container_sif_sha256  # type: ignore[union-attr]
    assert {"@id": f"configs/{v.result.provenance.config_hash}.json"} in action["object"]  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update({"@context": "https://w3id.org/ro/crate/1.1/context"}),
        lambda d: d["@graph"].pop(0),
        lambda d: d["@graph"][1].pop("datePublished"),
        lambda d: d["@graph"][1].update({"datePublished": "yesterday"}),
        lambda d: d["@graph"][1]["hasPart"].pop(),
        lambda d: d["@graph"][1].update({"conformsTo": []}),
    ],
)
def test_conformance_refuses_broken_crates(mutate) -> None:  # type: ignore[no-untyped-def]
    members = built("steady_optimization")
    doc = json.loads(members["ro-crate-metadata.json"])
    bad = copy.deepcopy(doc)
    mutate(bad)
    with pytest.raises(CrateError):
        check_rocrate(bad, set(members))


def test_prov_equivalence_detects_a_dropped_relation() -> None:
    members = built("steady_optimization")
    rocrate = json.loads(members["ro-crate-metadata.json"])
    prov = json.loads(members["prov.json"])
    prov["used"].pop(sorted(prov["used"])[0])
    with pytest.raises(CrateError, match="PROV equivalence"):
        check_prov_equivalence(rocrate, prov)
