#!/usr/bin/env bash
# scripts/download_ahmedml.sh
#
# Stage 08 — mirror AhmedML (CC-BY-SA-4.0) to TrueNAS `aero/datasets/ahmedml/`
# and register the result under DVC pointing at the MinIO remote.
#
# Upstream (Neil Ashton et al., Hugging Face): the dataset lives at
# https://huggingface.co/datasets/neashton/ahmedml. The 500 per-run
# directories carry an STL surface (`ahmed_<i>.stl`) plus a per-run
# force-moment CSV (`force_mom_<i>.csv`). The aero-platform-side join
# happens at the two ROOT-level CSVs (``geo_parameters_all.csv`` +
# ``force_mom_all.csv``); the per-run STLs are only consumed by
# Stage-09's DoMINO surface-field training.
#
# Two modes (control via STL_MODE env var):
#   STL_MODE=skip   (default) — pull only the two root CSVs (~150 KB);
#                              fast, lets the manifest land in seconds.
#   STL_MODE=full              — also pull every run_i/ STL (~80 GB).
#
# Run on `aero-build` (has direct internet egress; the host LXC does not).
# Operator-driven; intentionally NOT invoked from the test suite.
#
# Usage:
#   ssh root@aero-build
#   cd /opt/aero/repo
#   ./scripts/download_ahmedml.sh             # manifest-only (fast)
#   STL_MODE=full ./scripts/download_ahmedml.sh   # full STL mirror
#
# Idempotent: re-runs skip files already present.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATASET_DIR="${REPO_ROOT}/data/datasets/ahmedml"
HF_OWNER="neashton"
HF_PREFIX="ahmedml"
N_RUNS="${N_RUNS:-500}"
STL_MODE="${STL_MODE:-skip}"

mkdir -p "${DATASET_DIR}/cases"
cd "${DATASET_DIR}"

# 1. Root-level CSVs — the aero manifest builder joins these on `run`.
for f in "geo_parameters_all.csv" "force_mom_all.csv"; do
    if [[ ! -f "${f}" ]]; then
        url="https://huggingface.co/datasets/${HF_OWNER}/${HF_PREFIX}/resolve/main/${f}"
        echo ">> ${url}"
        curl -fsSL "${url}" -o "${f}"
    fi
done

# 2. Optional per-run STL mirror — only when STL_MODE=full.
if [[ "${STL_MODE}" == "full" ]]; then
    for i in $(seq 1 "${N_RUNS}"); do
        RUN="run_${i}"
        OUT="cases/${RUN}"
        mkdir -p "${OUT}"
        for f in "ahmed_${i}.stl" "force_mom_${i}.csv"; do
            if [[ -f "${OUT}/${f}" ]]; then continue; fi
            url="https://huggingface.co/datasets/${HF_OWNER}/${HF_PREFIX}/resolve/main/${RUN}/${f}"
            echo ">> ${url}"
            if ! curl -fsSL "${url}" -o "${OUT}/${f}"; then
                rm -f "${OUT}/${f}"
                echo "   (missing — skipping)"
            fi
        done
    done
fi

# 3. Build the aero `manifest.json` by joining the two root CSVs.
python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset ahmedml \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

# 4. Register with DVC + push to MinIO. dvc.yaml's `ingest-ahmedml` stage
# declares manifest.json + cases/ as outputs; the two root CSVs stay
# re-downloadable from upstream (KB-scale, no DVC tracking needed).
dvc commit -f manifest.json
if [[ "${STL_MODE}" == "full" ]]; then
    dvc commit -f cases/
fi
dvc push -r aero-minio

echo "AhmedML mirror complete (STL_MODE=${STL_MODE})."
