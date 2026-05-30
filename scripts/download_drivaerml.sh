#!/usr/bin/env bash
# scripts/download_drivaerml.sh — Stage 08 mirror of DrivAerML (CC-BY-SA-4.0).
#
# Upstream (Hugging Face): https://huggingface.co/datasets/neashton/drivaerml.
# Largest CC-BY-SA set in the bundle (~600 GB compressed). Operator must
# confirm TrueNAS `aero/datasets/` has ≥ 1 TB free margin before running.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATASET_DIR="${REPO_ROOT}/data/datasets/drivaerml"
HF_OWNER="neashton"
HF_PREFIX="drivaerml"
N_RUNS="${N_RUNS:-500}"

# Pre-flight: refuse to start if the TrueNAS NFS mount has < 1 TB free.
FREE_GB=$(df --output=avail -BG /mnt/aero/datasets 2>/dev/null | tail -1 | tr -dc '0-9')
if [[ -n "${FREE_GB}" && "${FREE_GB}" -lt 1000 ]]; then
    echo "ERROR: TrueNAS aero/datasets/ has < 1 TB free (${FREE_GB} GB)." >&2
    echo "Pull AhmedML + WindsorML first, free space, then retry." >&2
    exit 1
fi

mkdir -p "${DATASET_DIR}/cases"
cd "${DATASET_DIR}"

for i in $(seq 1 "${N_RUNS}"); do
    RUN="run_${i}"
    OUT="cases/${RUN}"
    mkdir -p "${OUT}"
    for f in "drivaer_${i}.stl" "force_mom_${i}.csv"; do
        if [[ -f "${OUT}/${f}" ]]; then continue; fi
        url="https://huggingface.co/datasets/${HF_OWNER}/${HF_PREFIX}/resolve/main/${RUN}/${f}"
        echo ">> ${url}"
        curl -fsSL "${url}" -o "${OUT}/${f}"
    done
done

python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset drivaerml \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

dvc add manifest.json cases/
dvc push -r aero-minio

echo "DrivAerML mirror complete; manifest + ${N_RUNS} cases registered under DVC."
