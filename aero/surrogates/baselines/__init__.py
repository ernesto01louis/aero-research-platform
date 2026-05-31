"""Stage-08 surrogate smoke baselines (MLP / FNO / MeshGraphNet).

Three concrete :class:`~aero.surrogates._common.base.Surrogate` subclasses,
each producing a :class:`~aero.surrogates._common.certificate.CertificateOfValidity`
with ``cert_status="smoke"``. The certificates are NOT publishable — they
exist to prove the plumbing (Surrogate protocol → fit → ingest → taint
propagation → set_certificate → MLflow tags → JSON artifact).

All three baselines lazy-import their heavy backend (torch / pyg) inside
``fit`` / ``predict`` so the package stays PLATFORM-NOT-HUB clean — base
``import aero.surrogates.baselines`` does not pull torch.
"""

from __future__ import annotations

from aero.surrogates.baselines.fno_smoke import FNOSmoke
from aero.surrogates.baselines.mgn_smoke import MGNSmoke
from aero.surrogates.baselines.mlp_baseline import MLPBaseline

__all__ = ["FNOSmoke", "MGNSmoke", "MLPBaseline"]
