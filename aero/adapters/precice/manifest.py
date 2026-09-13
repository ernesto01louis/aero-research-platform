"""``aero-manifest.json`` renderers — one per source of a coupled case's bytes.

**Why these are free functions over primitives, hand-building every dict, and never calling
``model_dump()``.** ``json.dumps(..., sort_keys=True)`` sorts *recursively*. A single new
optional field on :class:`~aero.adapters.precice.case.MaterializedFile` or
:class:`~aero.adapters.precice.case.DeclaredMutation` would therefore rewrite all 94 ``files``
entries of a Stage-19 manifest, and a new top-level key would re-sort the whole document —
silently, at the next unrelated model change. The Stage-19 bundle's manifest is a committed
golden and backs a closed, tagged verdict, so its bytes are a contract, not an artifact.

The defence is to version the **shape**, not to add fields: the tutorial schema below is v1
and is frozen; authored cases get their own emitter and their own schema. The emitter is
chosen by an exhaustive ``match`` on the source discriminator at the one call site
(``PreciceCoupledSolver._write_case``), so a third source type in a future stage is a type
error rather than a silent fall-through into the tutorial schema.

Schema v1 (tutorial), emitted key order after ``sort_keys=True``::

    {"case_dir": str,
     "declared_mutations": [{after_sha256, before_sha256, detail, kind, path}, ...],
     "files": [{path, sha256}, ...],
     "pin": {archive_sha256, branch, commit, repo}}

with ``indent=2`` and exactly one trailing newline. Reproduced byte-for-byte in every
pre-Stage-20 bundle; pinned by ``tests/stage_20/test_stage19_materialization_is_byte_identical.py``
against ``fixtures/materialization/golden-aero-manifest.json`` and
``golden-fsi3-aero-manifest.json``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from aero.adapters.precice.case import (
    AuthoredSource,
    CoupledCaseError,
    DeclaredMutation,
    MaterializedFile,
    TutorialPin,
)

__all__ = [
    "AUTHORED_MANIFEST_SCHEMA",
    "TUTORIAL_MANIFEST_SCHEMA",
    "render_authored_manifest_json",
    "render_tutorial_manifest_json",
]

TUTORIAL_MANIFEST_SCHEMA = 1
AUTHORED_MANIFEST_SCHEMA = 2


def _dump(document: dict[str, object]) -> str:
    """The one serialization used by every schema: 2-space indent, sorted, one newline."""
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def render_tutorial_manifest_json(
    *,
    pin: TutorialPin,
    case_dir_rel: str,
    files: Sequence[MaterializedFile],
    mutations: Sequence[DeclaredMutation],
) -> str:
    """Render schema v1 — a case laid down from a pinned upstream tutorial.

    Every key is spelled out here on purpose. Do not reintroduce ``model_dump()``: see the
    module docstring for what that costs.
    """
    for mutation in mutations:
        if mutation.kind == "authored":
            raise CoupledCaseError(
                f"tutorial manifest schema v{TUTORIAL_MANIFEST_SCHEMA} cannot describe an "
                f"authored mutation ({mutation.path!r}) — an authored case must use "
                "render_authored_manifest_json"
            )
        if mutation.before_sha256 is None:
            raise CoupledCaseError(
                f"tutorial mutation {mutation.kind!r} on {mutation.path!r} has no "
                "before_sha256; every tutorial mutation replaces pinned bytes"
            )
    return _dump(
        {
            "pin": {
                "repo": pin.repo,
                "branch": pin.branch,
                "commit": pin.commit,
                "archive_sha256": pin.archive_sha256,
            },
            "case_dir": case_dir_rel,
            "files": [{"path": f.path, "sha256": f.sha256} for f in files],
            "declared_mutations": [
                {
                    "kind": m.kind,
                    "path": m.path,
                    "detail": m.detail,
                    "before_sha256": m.before_sha256,
                    "after_sha256": m.after_sha256,
                }
                for m in mutations
            ],
        }
    )


def render_authored_manifest_json(
    *,
    source: AuthoredSource,
    case_dir_rel: str,
    files: Sequence[MaterializedFile],
    mutations: Sequence[DeclaredMutation],
    spec_sha256: str,
) -> str:
    """Render schema v2 — a case this platform authored, with no upstream pin.

    ``spec_sha256`` is the canonical-JSON digest of the spec that ``config_hash`` consumes.
    Carrying it here is one line that proves the manifest on disk and the MLflow tag describe
    the same spec; without it the two are merely believed to agree.
    """
    return _dump(
        {
            "schema": AUTHORED_MANIFEST_SCHEMA,
            "authored": {
                "case_dir_name": source.case_dir_name,
                "renderer_version": source.renderer_version,
                "template": source.template,
                "template_sha256": source.template_sha256,
                "spec_sha256": spec_sha256,
            },
            "case_dir": case_dir_rel,
            "files": [{"path": f.path, "sha256": f.sha256} for f in files],
            "declared_mutations": [
                {
                    "kind": m.kind,
                    "path": m.path,
                    "detail": m.detail,
                    "before_sha256": m.before_sha256,
                    "after_sha256": m.after_sha256,
                }
                for m in mutations
            ],
        }
    )
