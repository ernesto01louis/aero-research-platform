"""Stage 09 — pluggable DVC-remote storage backend (cloud / nas / minio, ADR-011).

Verifies the config-switchable remotes resolve correctly — the whole point is
that flipping cloud->NAS is config-only, zero code change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from omegaconf import OmegaConf

pytestmark = pytest.mark.stage_09

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("profile", "remote", "endpoint"),
    [
        ("cloud", "aero-cloud", ""),
        ("nas", "aero-nas", "http://192.168.2.100:9000"),
        ("minio", "aero-minio", "http://192.168.2.234:9000"),
        ("nfs", "aero-nfs", ""),
    ],
)
def test_storage_profile(profile: str, remote: str, endpoint: str) -> None:
    cfg = OmegaConf.load(_REPO_ROOT / "conf" / "storage" / f"{profile}.yaml")
    assert cfg.dvc_remote == remote
    assert cfg.s3_endpoint == endpoint


def test_default_storage_is_cloud() -> None:
    cfg = OmegaConf.load(_REPO_ROOT / "conf" / "config.yaml")
    defaults = OmegaConf.to_container(cfg.defaults, resolve=True)
    assert isinstance(defaults, list)
    storage_default = next(
        (d["storage"] for d in defaults if isinstance(d, dict) and "storage" in d), None
    )
    assert storage_default == "cloud"


def test_compose_resolves_storage_override() -> None:
    from hydra import compose, initialize_config_dir
    from hydra.core.global_hydra import GlobalHydra

    GlobalHydra.instance().clear()
    with initialize_config_dir(version_base=None, config_dir=str(_REPO_ROOT / "conf")):
        cfg = compose(config_name="config", overrides=["case=naca0012", "storage=nas"])
    assert cfg.storage.dvc_remote == "aero-nas"
    assert cfg.storage.s3_endpoint == "http://192.168.2.100:9000"


def test_domino_config_uses_cloud_remote() -> None:
    cfg = OmegaConf.load(_REPO_ROOT / "conf" / "surrogate" / "domino.yaml")
    assert cfg.storage.dvc_remote == "aero-cloud"
    assert cfg.dataset.id == "drivaerml"
