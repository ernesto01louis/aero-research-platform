#!/usr/bin/env bash
# scripts/download_drivaerml.sh — DrivAerML surface-model pull (CC-BY-SA-4.0).
#
# Upstream (Hugging Face, git-LFS): https://huggingface.co/datasets/neashton/drivaerml
# (~31 TB full, 500 runs). Stage 09's DoMINO is a SURFACE model, so it needs the
# geometry + the surface fields but NOT the (~50 GB/run) volume fields:
#   FILESET=surface (default) → per run: drivaer_i.stl (~142 MB)
#                                       + boundary_i.vtp (~660 MB)  ← surface p / WSS
#                                       + the small per-run CSVs
#   FILESET=stl               → per run: drivaer_i.stl + the small CSVs only
# The volume files (volume_i.vtu*) are NEVER pulled here.
#
# Uses huggingface_hub.snapshot_download (resumable, parallel via hf_transfer,
# follows the LFS 307 redirects) instead of a serial curl loop. Two snapshots
# keep the per-run folders under cases/ and the root join-CSVs at the root:
#   <DATASET_DIR>/cases/run_i/{drivaer_i.stl,boundary_i.vtp,*.csv}
#   <DATASET_DIR>/{geo_parameters_all.csv,force_mom_all.csv}
#
# On aero-dev, <DATASET_DIR>/cases is a symlink to the NFS dataset
# (/mnt/aero/datasets/drivaerml/cases) so the ~401 GB lands on TrueNAS while the
# small .dvc pointers + manifest stay in the repo tree. See the Stage-09 handoff.
#
# Env knobs (all optional):
#   DATASET_DIR     target dir (default <REPO_ROOT>/data/datasets/drivaerml)
#   N_RUNS          number of runs to pull, 1..N (default 500)
#   FILESET         surface (default) | stl
#   DVC_REMOTE      dvc remote for the push (default aero-nfs)
#   DVC_TRACK       1 = dvc add + push (default) · 0 = download + manifest only (smoke)
#   HF_MAX_WORKERS  parallel download workers (default 8)

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
DATASET_DIR="${DATASET_DIR:-${REPO_ROOT}/data/datasets/drivaerml}"
HF_REPO="neashton/drivaerml"
N_RUNS="${N_RUNS:-500}"
FILESET="${FILESET:-surface}"
DVC_REMOTE="${DVC_REMOTE:-aero-nfs}"
DVC_TRACK="${DVC_TRACK:-1}"
HF_MAX_WORKERS="${HF_MAX_WORKERS:-8}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"

mkdir -p "${DATASET_DIR}/cases"

# --- pre-flight: free space on the target filesystem --------------------------
PER_RUN_GB=1                                   # ~0.8 GB surface/run; round up for margin
NEED_GB=$(( N_RUNS * PER_RUN_GB + 50 ))
FREE_GB=$(df -PBG "${DATASET_DIR}/cases" | awk 'NR==2{gsub(/G/,"",$4); print $4}')
if [[ -n "${FREE_GB}" && "${FREE_GB}" -lt "${NEED_GB}" ]]; then
    echo "ERROR: $(readlink -f "${DATASET_DIR}/cases") has ${FREE_GB} GB free; need ~${NEED_GB} GB for ${N_RUNS} runs." >&2
    exit 1
fi
echo ">> target=${DATASET_DIR} runs=${N_RUNS} fileset=${FILESET} free=${FREE_GB:-?}GB need~${NEED_GB}GB"

# --- download (snapshot_download does the work; config passed via env) ---------
DATASET_DIR="${DATASET_DIR}" HF_REPO="${HF_REPO}" N_RUNS="${N_RUNS}" \
FILESET="${FILESET}" HF_MAX_WORKERS="${HF_MAX_WORKERS}" \
python3 - <<'PY'
import os
from huggingface_hub import snapshot_download

dataset_dir = os.environ["DATASET_DIR"]
repo = os.environ["HF_REPO"]
n = int(os.environ["N_RUNS"])
fileset = os.environ["FILESET"]
workers = int(os.environ["HF_MAX_WORKERS"])

# 1) root join-CSVs -> dataset root (the manifest builder reads these).
snapshot_download(
    repo_id=repo, repo_type="dataset", local_dir=dataset_dir,
    allow_patterns=["geo_parameters_all.csv", "force_mom_all.csv"],
    max_workers=workers,
)

# 2) per-run files -> dataset_dir/cases/run_i/...
per_run = ["drivaer_{i}.stl"]
if fileset == "surface":
    per_run.append("boundary_{i}.vtp")          # surface pressure + wall-shear
per_run += ["force_mom_{i}.csv", "force_mom_constref_{i}.csv",
            "geo_parameters_{i}.csv", "geo_ref_{i}.csv"]
patterns = [f"run_{i}/" + p.format(i=i) for i in range(1, n + 1) for p in per_run]

snapshot_download(
    repo_id=repo, repo_type="dataset",
    local_dir=os.path.join(dataset_dir, "cases"),
    allow_patterns=patterns, max_workers=workers,
)
print(f"snapshot_download complete: {n} runs, fileset={fileset}")
PY

# --- manifest (joins the two root CSVs; per-run files are not consulted) -------
python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset drivaerml \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

echo ">> file counts under cases/:"
echo "   drivaer_*.stl : $(find "${DATASET_DIR}/cases" -name 'drivaer_*.stl' | wc -l)"
if [[ "${FILESET}" == "surface" ]]; then
    echo "   boundary_*.vtp: $(find "${DATASET_DIR}/cases" -name 'boundary_*.vtp' | wc -l)"
fi

# --- DVC (gated so the smoke can inspect footprint before committing) ----------
if [[ "${DVC_TRACK}" == "1" ]]; then
    cd "${REPO_ROOT}"
    dvc add data/datasets/drivaerml/cases data/datasets/drivaerml/manifest.json
    dvc push -r "${DVC_REMOTE}"
    echo ">> dvc add + push -r ${DVC_REMOTE} complete"
fi

echo "DrivAerML ${FILESET} pull complete (N_RUNS=${N_RUNS})."
