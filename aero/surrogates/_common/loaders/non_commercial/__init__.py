"""CC-BY-NC dataset loaders — the structural quarantine boundary.

This subpackage is licence-segregated by construction. Any module under
``aero/`` that imports from ``aero.surrogates._common.loaders.non_commercial``
MUST satisfy one of:

* Produce a :class:`~aero.surrogates._common.certificate.CertificateOfValidity`
  with ``non_commercial=True``; this is enforced automatically because every
  ``__getitem__`` here yields :class:`~aero.surrogates._common.base.TaintedSample`,
  which flips :attr:`Surrogate._non_commercial` via :meth:`Surrogate.ingest`.
* OR carry the ``# non-commercial: justified`` pragma on the import line,
  documenting an audited exception (test fixtures, license-aware tooling).

The ``.github/workflows/non-commercial-fence.yml`` CI workflow rejects any
PR that imports from this subpackage without one of those two conditions.
This is the first of three quarantine layers (structural separator +
constructor guard + tainted-sample union — see ADR-008 §D4).
"""

from __future__ import annotations

from aero.surrogates._common.loaders.non_commercial.drivaernet_plus_plus import (
    DrivAerNetPlusPlusDataset,
)

__all__ = ["DrivAerNetPlusPlusDataset"]
