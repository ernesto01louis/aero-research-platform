#!/usr/bin/env bash
# scripts/download_drivaerml.sh — Stage 08 mirror of DrivAerML (CC-BY-SA-4.0).
#
# Upstream (Hugging Face): https://huggingface.co/datasets/neashton/drivaerml.
# Largest CC-BY-SA set in the bundle. STL_MODE controls whether per-run STLs
# are mirrored — `skip` (default) just pulls the root CSVs for the manifest
# (~150 KB); `full` mirrors every run_i/ STL (~600 GB total).
#
# Pre-flight: refuse to start the full STL pull if TrueNAS aero/datasets/
# has < 1 TB free margin. The manifest-only path has no such check (it's
# tiny).

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATASET_DIR="${REPO_ROOT}/data/datasets/drivaerml"
HF_OWNER="neashton"
HF_PREFIX="drivaerml"
N_RUNS="${N_RUNS:-500}"
STL_MODE="${STL_MODE:-skip}"

mkdir -p "${DATASET_DIR}/cases"
cd "${DATASET_DIR}"

if [[ "${STL_MODE}" == "full" ]]; then
    FREE_GB=$(df --output=avail -BG /mnt/aero/datasets 2>/dev/null | tail -1 | tr -dc '0-9')
    if [[ -n "${FREE_GB}" && "${FREE_GB}" -lt 1000 ]]; then
        echo "ERROR: TrueNAS aero/datasets/ has < 1 TB free (${FREE_GB} GB)." >&2
        echo "Pull AhmedML + WindsorML first, free space, then retry." >&2
        exit 1
    fi
fi

for f in "geo_parameters_all.csv" "force_mom_all.csv"; do
    if [[ ! -f "${f}" ]]; then
        url="https://huggingface.co/datasets/${HF_OWNER}/${HF_PREFIX}/resolve/main/${f}"
        echo ">> ${url}"
        curl -fsSL "${url}" -o "${f}"
    fi
done

if [[ "${STL_MODE}" == "full" ]]; then
    for i in $(seq 1 "${N_RUNS}"); do
        RUN="run_${i}"
        OUT="cases/${RUN}"
        mkdir -p "${OUT}"
        for f in "drivaer_${i}.stl" "force_mom_${i}.csv"; do
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

python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset drivaerml \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

# dvc.yaml's `ingest-drivaerml` stage declares manifest.json + cases/ as
# outputs; the two root CSVs stay re-downloadable from upstream.
dvc commit -f manifest.json
if [[ "${STL_MODE}" == "full" ]]; then
    dvc commit -f cases/
fi
dvc push -r aero-minio

echo "DrivAerML mirror complete (STL_MODE=${STL_MODE})."
