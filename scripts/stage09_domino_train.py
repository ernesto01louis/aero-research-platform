#!/usr/bin/env python3
"""Stage 09 — on-pod DoMINO training entrypoint.

Runs INSIDE ``physicsnemo.sif`` on the RunPod H100 pod (or an aero LXC for a
local-GPU dry-run), submitted by ``aero surrogate train --baseline domino``. The
full reproducible flow:

1. resolve ``conf/surrogate/domino.yaml`` (Hydra/OmegaConf);
2. ``dvc pull`` the DrivAerML subset from the configured storage remote
   (cloud-now / NAS-later — ``cfg.storage.dvc_remote``; ADR-011);
3. compute the four-fold provenance tuple (container SIF = ``physicsnemo.sif``);
4. ``train_domino`` — no-PC baseline + the Predictor-Corrector recipe, then the
   gated smoke->validated cert (held-out Cd MAE p95 < 5%);
5. log the EIGHT surrogate provenance tags + the cert JSON artifact + the
   per-target held-out metrics + the observed PC speedup to MLflow;
6. save the trained checkpoint as an MLflow artifact (NOT git — Hard Rule);
7. run the ``surrogate_vv`` cross-check (predict held-out cases vs CFD) and log
   the report artifact — the falsifiable evidence behind the cert.

GPU seams (mesh IO, the DoMINO net) are inside the PhysicsNeMo engine and are
validated on the first pod run (cluster-gated, the Stage 07/08 pattern). Heavy
imports are deferred into ``main`` so the file parses + imports host-side.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# DoMINO trains on DrivAerML (CC-BY-SA) — the per-target order for metric labels.
_TARGET_NAMES = ("cd", "cl", "clf", "clr", "cs")


def _dvc_pull(repo_root: Path, remote: str, dvc_path: str) -> None:
    """Pull a DVC target from the chosen remote (cloud-now / NAS-later)."""
    cmd = [sys.executable.replace("python", "dvc"), "pull", "-r", remote, dvc_path]
    # Fall back to a bare `dvc` if the interpreter-adjacent shim isn't present.
    if not Path(cmd[0]).exists():
        cmd[0] = "dvc"
    print(f"[stage09] dvc pull -r {remote} {dvc_path}", flush=True)
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"dvc pull failed (rc={proc.returncode}): {proc.stderr.strip()}")


def _build_vv_cases(surrogate: Any, loader: Any, cases_root: Path, n: int) -> list[Any]:
    """Build SurrogateVVCase set from the held-out split (cluster-gated mesh IO).

    Packs each held-out case's surface into the DoMINO input via the surrogate's
    engine and pairs it with the loader's CFD-reference coefficients. Raises if
    the engine/mesh backend is unavailable (host/dry-run); the caller logs the
    surrogate_vv step as deferred rather than failing the whole run.
    """
    from aero.surrogates.domino.model import DominoEngineUnavailable
    from aero.vv.surrogate import SurrogateVVCase

    engine = surrogate._resolved_engine()
    pack = getattr(engine, "pack_surface", None)
    if pack is None:
        raise DominoEngineUnavailable("engine has no pack_surface — validated on first pod run")
    cases: list[Any] = []
    for idx in range(min(n, len(loader))):
        sample = loader[idx]
        surface = pack(sample.case_id, cases_root)
        cases.append(
            SurrogateVVCase(
                case_id=sample.case_id,
                surface_input=surface,
                reference=sample.targets,
                target_names=_TARGET_NAMES,
            )
        )
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="conf/surrogate/domino.yaml")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--n-vv-cases", type=int, default=8)
    args = parser.parse_args(argv)

    # Heavy imports here so the module parses + imports host-side without extras.
    from aero.provenance.four_fold import compute_provenance
    from aero.surrogates._common._dataset_pick import build_loader
    from aero.surrogates._common.loaders import dataset_hash
    from aero.surrogates._common.provenance import SurrogateProvenanceTags, hparam_hash
    from aero.surrogates.domino import train_domino
    from omegaconf import OmegaConf

    repo_root = Path.cwd()
    cfg = OmegaConf.load(args.config)
    resolved: dict[str, Any] = OmegaConf.to_container(cfg, resolve=True)  # type: ignore[assignment]

    storage = resolved.get("storage", {}) or {}
    dataset = resolved.get("dataset", {}) or {}
    dvc_remote = str(storage.get("dvc_remote", "aero-cloud"))
    dvc_path = str(dataset.get("dvc_path", "data/datasets/drivaerml"))
    cases_root = repo_root / str(dataset.get("cases_root", "data/datasets/drivaerml/cases"))

    # 1) stage the dataset from the chosen remote (cloud-now / NAS-later).
    _dvc_pull(repo_root, dvc_remote, dvc_path)

    # 2) four-fold provenance — container SIF is physicsnemo.sif (Stage 09).
    provenance = compute_provenance(
        repo_root=repo_root,
        container_sif="physicsnemo.sif",
        resolved_config=resolved,
        allow_dirty=args.allow_dirty,
    )
    print(f"[stage09] provenance git_sha={provenance.git_sha}", flush=True)

    # 3) loader + train-data hash.
    loader = build_loader(dataset_id=str(dataset.get("id", "drivaerml")), repo_root=repo_root)
    train_dvc_hash = dataset_hash(repo_root, loader.dvc_path)

    # 4) baseline + Predictor-Corrector + gated cert.
    result = train_domino(
        resolved_config=resolved,
        data=iter(loader),
        train_dataset_dvc_hash=train_dvc_hash,
        dataset_id=loader.dataset_id,
        cases_root=cases_root,
    )
    cert = result.certificate
    print(
        f"[stage09] cert_status={cert.cert_status} "
        f"pc_applied={result.predictor_corrector_applied} "
        f"speedup={result.speedup_factor}",
        flush=True,
    )

    # 5-7) MLflow: eight tags + cert + metrics + checkpoint + surrogate_vv.
    import mlflow

    mlflow.set_experiment("aero-surrogates")
    with mlflow.start_run(run_name=f"domino-{loader.dataset_id}") as run:
        tags = SurrogateProvenanceTags.from_certificate(
            provenance=provenance,
            cert=cert,
            hparam_hash=hparam_hash(resolved.get("train", {})),
        )
        for key, value in tags.as_mlflow_tags().items():
            mlflow.set_tag(key, value)

        for metric, q in result.held_out_metrics.items():
            mlflow.log_metric(f"{metric}_p50", q.p50)
            mlflow.log_metric(f"{metric}_p95", q.p95)
            mlflow.log_metric(f"{metric}_p99", q.p99)
        if result.speedup_factor is not None:
            mlflow.log_metric("pc_speedup_factor", result.speedup_factor)
        if result.baseline_seconds is not None:
            mlflow.log_metric("baseline_seconds", result.baseline_seconds)
        if result.pc_seconds is not None:
            mlflow.log_metric("pc_seconds", result.pc_seconds)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cert_file = tmp_path / "domino.json"
            cert_file.write_text(json.dumps(cert.model_dump(mode="json"), indent=2, default=str))
            mlflow.log_artifact(str(cert_file), artifact_path="certificates")

            ckpt = tmp_path / "domino.pt"
            try:
                result.surrogate.save_checkpoint(ckpt)
                mlflow.log_artifact(str(ckpt), artifact_path="models")
            except Exception as exc:  # pragma: no cover — cluster-gated
                print(f"[stage09] checkpoint save deferred: {exc!r}", flush=True)

            # surrogate_vv cross-check — best-effort (needs the mesh engine).
            try:
                from aero.vv.surrogate import compare_surrogate_cfd

                cases = _build_vv_cases(result.surrogate, loader, cases_root, args.n_vv_cases)
                report = compare_surrogate_cfd(result.surrogate, cases)
                vv_file = tmp_path / "surrogate_vv.json"
                vv_file.write_text(report.to_json())
                mlflow.log_artifact(str(vv_file), artifact_path="surrogate_vv")
                print(
                    f"[stage09] surrogate_vv: passed={report.passed} "
                    f"cd_within_tol={report.cd_within_tolerance}",
                    flush=True,
                )
            except Exception as exc:  # pragma: no cover — cluster-gated mesh IO
                print(f"[stage09] surrogate_vv deferred: {exc!r}", flush=True)

        print(f"[stage09] logged DoMINO run {run.info.run_id}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
