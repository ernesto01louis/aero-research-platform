"""Dataset-id-to-loader dispatch for the Stage-08 ``aero surrogate train`` CLI.

Maps the string id from a Hydra config (``ahmedml`` / ``windsorml`` /
``drivaerml`` / ``drivaernet_plus_plus``) to a constructed loader instance.
Centralised here so the CLI does not have to import every loader module
eagerly. The DrivAerNet++ branch carries the ``# non-commercial: justified``
pragma — this is the CLI's audited exception (the cert that the surrogate
issues afterwards still carries the propagated ``non_commercial=True``
taint, satisfying the structural fence).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_loader(
    *,
    dataset_id: str,
    repo_root: Path,
    acknowledge_noncommercial: bool = False,
) -> Any:
    """Construct the named loader; raise on an unknown id.

    Local imports per branch keep PLATFORM-NOT-HUB clean: importing this
    module does not pull every loader's dependency chain.
    """
    if dataset_id == "ahmedml":
        from aero.surrogates._common.loaders.ahmedml import AhmedMLDataset

        return AhmedMLDataset(repo_root=repo_root)
    if dataset_id == "windsorml":
        from aero.surrogates._common.loaders.windsorml import WindsorMLDataset

        return WindsorMLDataset(repo_root=repo_root)
    if dataset_id == "drivaerml":
        from aero.surrogates._common.loaders.drivaerml import DrivAerMLDataset

        return DrivAerMLDataset(repo_root=repo_root)
    if dataset_id == "drivaernet_plus_plus":
        # non-commercial: justified
        from aero.surrogates._common.loaders.non_commercial.drivaernet_plus_plus import (
            DrivAerNetPlusPlusDataset,
        )

        return DrivAerNetPlusPlusDataset(
            repo_root=repo_root,
            acknowledge_noncommercial=acknowledge_noncommercial,
        )
    raise ValueError(
        f"unknown dataset_id {dataset_id!r}; expected 'ahmedml', 'windsorml', "
        "'drivaerml', or 'drivaernet_plus_plus'"
    )
