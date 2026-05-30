#!/usr/bin/env bash
# scripts/download_windsorml.sh — Stage 08 mirror of WindsorML (CC-BY-SA-4.0).
#
# Upstream (Hugging Face): https://huggingface.co/datasets/neashton/windsorml.
# Same root-CSV + per-run-STL pattern as AhmedML. STL_MODE controls whether
# the per-run STLs are mirrored (default skip; ~30 GB).
#
# See scripts/download_ahmedml.sh for the full pattern + commentary.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATASET_DIR="${REPO_ROOT}/data/datasets/windsorml"
HF_OWNER="neashton"
HF_PREFIX="windsorml"
N_RUNS="${N_RUNS:-355}"
STL_MODE="${STL_MODE:-skip}"

mkdir -p "${DATASET_DIR}/cases"
cd "${DATASET_DIR}"

for f in "geo_parameters_all.csv" "force_mom_all.csv"; do
    if [[ ! -f "${f}" ]]; then
        url="https://huggingface.co/datasets/${HF_OWNER}/${HF_PREFIX}/resolve/main/${f}"
        echo ">> ${url}"
        curl -fsSL "${url}" -o "${f}"
    fi
done

if [[ "${STL_MODE}" == "full" ]]; then
    for i in $(seq 0 "$((N_RUNS - 1))"); do
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
fi

python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset windsorml \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

# dvc.yaml's `ingest-windsorml` stage declares manifest.json + cases/ as
# outputs; the two root CSVs stay re-downloadable from upstream.
dvc commit -f manifest.json
if [[ "${STL_MODE}" == "full" ]]; then
    dvc commit -f cases/
fi
dvc push -r aero-minio

echo "WindsorML mirror complete (STL_MODE=${STL_MODE})."
