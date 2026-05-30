#!/usr/bin/env bash
# scripts/download_windsorml.sh — Stage 08 mirror of WindsorML (CC-BY-SA-4.0).
#
# Upstream (Hugging Face): https://huggingface.co/datasets/neashton/windsorml.
# Same per-run pattern as AhmedML; the integrated coefficients ride alongside
# the STL surface mesh under `run_{i}/`.
#
# See scripts/download_ahmedml.sh for the full pattern + commentary.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATASET_DIR="${REPO_ROOT}/data/datasets/windsorml"
HF_OWNER="neashton"
HF_PREFIX="windsorml"
N_RUNS="${N_RUNS:-355}"   # WindsorML ships 355 runs (per upstream catalogue);
                          # override via N_RUNS for a smoke subset.

mkdir -p "${DATASET_DIR}/cases"
cd "${DATASET_DIR}"

for i in $(seq 1 "${N_RUNS}"); do
    RUN="run_${i}"
    OUT="cases/${RUN}"
    mkdir -p "${OUT}"
    for f in "windsor_${i}.stl" "force_mom_${i}.csv"; do
        if [[ -f "${OUT}/${f}" ]]; then continue; fi
        url="https://huggingface.co/datasets/${HF_OWNER}/${HF_PREFIX}/resolve/main/${RUN}/${f}"
        echo ">> ${url}"
        curl -fsSL "${url}" -o "${OUT}/${f}"
    done
done

python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset windsorml \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

dvc add manifest.json cases/
dvc push -r aero-minio

echo "WindsorML mirror complete; manifest + ${N_RUNS} cases registered under DVC."
