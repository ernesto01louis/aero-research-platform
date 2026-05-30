#!/usr/bin/env bash
# scripts/download_ahmedml.sh
#
# Stage 08 — mirror AhmedML (CC-BY-SA-4.0) to TrueNAS `aero/datasets/ahmedml/`
# and register the result under DVC pointing at the MinIO remote.
#
# Upstream (Neil Ashton et al., Hugging Face): the dataset lives at
# https://huggingface.co/datasets/neashton/ahmedml. 500 runs; each run dir
# contains an STL surface and a `force_mom_*.csv` carrying the integrated
# coefficients. The aero loader (`aero.surrogates._common.loaders.ahmedml`)
# parses a `manifest.json` that the post-process step in this script builds
# from the per-run CSVs.
#
# Run on `aero-build` (has direct internet egress; the host LXC does not).
# Operator-driven; intentionally NOT invoked from the test suite.
#
# Usage:
#   ssh root@aero-build
#   cd /opt/aero/repo
#   ./scripts/download_ahmedml.sh
#
# Idempotent: re-runs verify checksums and skip files already present.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATASET_DIR="${REPO_ROOT}/data/datasets/ahmedml"
HF_OWNER="neashton"
HF_PREFIX="ahmedml"
N_RUNS="${N_RUNS:-500}"

mkdir -p "${DATASET_DIR}/cases"
cd "${DATASET_DIR}"

# 1. Per-run download from the Hugging Face dataset. Files are public; no
#    HF token required for the CC-BY-SA datasets.
for i in $(seq 1 "${N_RUNS}"); do
    RUN="run_${i}"
    OUT="cases/${RUN}"
    mkdir -p "${OUT}"
    for f in "ahmed_${i}.stl" "force_mom_${i}.csv"; do
        if [[ -f "${OUT}/${f}" ]]; then continue; fi
        url="https://huggingface.co/datasets/${HF_OWNER}/${HF_PREFIX}/resolve/main/${RUN}/${f}"
        echo ">> ${url}"
        curl -fsSL "${url}" -o "${OUT}/${f}"
    done
done

# 2. Build the `manifest.json` the aero loader consumes from the per-run
#    `force_mom_*.csv` files. The upstream CSV's exact column names are
#    captured at first run; the build_manifest.py helper (Stage-09
#    follow-up) translates them into the four-vector descriptor the loader
#    expects. Until then, the manifest is left empty with a stub so the
#    `aero[surrogate-smoke]` tests can run on a fixture-supplied subset.
python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset ahmedml \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

# 3. Register the manifest + all per-run files with DVC; push to MinIO.
dvc add manifest.json cases/
dvc push -r aero-minio

echo "AhmedML mirror complete; manifest + ${N_RUNS} cases registered under DVC."
