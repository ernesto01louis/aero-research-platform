"""Stage 04 — hermetic tests for the Hydra config tree and the CaseSpec boundary.

Composes the real `conf/` tree and verifies it resolves into a strict
`CaseSpec`. Run in the default CI suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.schemas import CaseSpec
from aero.cli import _case_spec_from_cfg, _compose_config
from omegaconf import OmegaConf

pytestmark = pytest.mark.stage_04

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_naca0012_resolves_to_casespec() -> None:
    cfg = _compose_config(_REPO_ROOT, "naca0012")
    spec = _case_spec_from_cfg(cfg)
    assert isinstance(spec, CaseSpec)
    assert spec.name == "naca0012"
    assert spec.reynolds == 6.0e6
    assert isinstance(spec.reynolds, float)


def test_compose_includes_mlflow_and_provenance_layers() -> None:
    cfg = _compose_config(_REPO_ROOT, "naca0012")
    assert cfg.mlflow.tracking_uri.startswith("http://")
    assert cfg.mlflow.tracking_uri.endswith(":5000")
    assert cfg.provenance.container_sif == "openfoam-esi.sif"


def test_case_yaml_covers_every_casespec_field() -> None:
    """The case YAML must list every CaseSpec field explicitly (ADR-004).

    A field present on `CaseSpec` but absent from the YAML would fall outside
    the `config_hash` — a silent provenance gap.
    """
    case_yaml = _REPO_ROOT / "conf" / "case" / "naca0012.yaml"
    yaml_keys = set(OmegaConf.load(case_yaml).keys())
    assert yaml_keys == set(CaseSpec.model_fields)


def test_resolved_case_is_json_hashable() -> None:
    cfg = _compose_config(_REPO_ROOT, "naca0012")
    resolved = OmegaConf.to_container(cfg, resolve=True)
    assert isinstance(resolved, dict)
    assert "case" in resolved and "mlflow" in resolved and "provenance" in resolved
