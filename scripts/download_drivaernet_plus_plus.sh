#!/usr/bin/env bash
# scripts/download_drivaernet_plus_plus.sh — DrivAerNet++ (CC-BY-NC-4.0).
#
# QUARANTINED dataset (ADR-008 §D4). Operator must export
# `AERO_ACKNOWLEDGE_NONCOMMERCIAL=1`; the acknowledgment is mirrored into
# MLflow on every training run that touches the dataset.
#
# Upstream: https://github.com/Mohamedelrefaie/DrivAerNet — CC-BY-NC-4.0.
#
# Two modes (select via AERO_DRIVAERNET_MODE):
#
#   - lite  (default): ~2 MB. Pulls the CSV summaries (Cd, frontal area,
#           parametric design variables) and the canonical train/val/test
#           splits via the upstream Dropbox + GitHub links. No Dataverse
#           access, no guestbook flow. Enough for descriptor → Cd baselines
#           once the manifest builder is revised; see reference.md.
#
#   - full : multi-GB. Uses the Dataverse Native API to pull a specific
#           sub-dataset by DOI. The 4 non-CFD sub-datasets are 75/213/436/
#           443 GB; the CFD sub-dataset is 10.6 TB. Sub-datasets larger than
#           Annotations sit behind Dataverse's guestbook prompt; the Native
#           API returns 400 without a guestbook response — upstream recommends
#           Globus for the big pulls. This mode is plumbed but the
#           guestbook bypass is not wired (Stage-09 work).

set -euo pipefail

if [[ "${AERO_ACKNOWLEDGE_NONCOMMERCIAL:-0}" != "1" ]]; then
    cat >&2 <<'BANNER'
DrivAerNet++ is licensed CC-BY-NC-4.0. Artifacts trained on this dataset
carry the non-commercial constraint and cannot be reused commercially.

Re-run with:
    AERO_ACKNOWLEDGE_NONCOMMERCIAL=1 ./scripts/download_drivaernet_plus_plus.sh
BANNER
    exit 2
fi

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATASET_DIR="${REPO_ROOT}/data/datasets/drivaernet_plus_plus"
MODE="${AERO_DRIVAERNET_MODE:-lite}"

mkdir -p "${DATASET_DIR}/cases" "${DATASET_DIR}/splits"
cd "${DATASET_DIR}"

case "${MODE}" in
    lite)
        echo ">> DrivAerNet++ lite-mode pull (CSVs + splits, ~2 MB)"

        # Drag values: 8,121 cars × Drag_Value
        curl -fLs \
            "https://www.dropbox.com/scl/fi/2rtchqnpmzy90uwa9wwny/DrivAerNetPlusPlus_Cd_8k_Updated.csv?rlkey=vjnjurtxfuqr40zqgupnks8sn&st=6dx1mfct&dl=1" \
            -o cases/DrivAerNetPlusPlus_Cd_8k_Updated.csv

        # Frontal areas: 8,007 cars × Frontal Area (m²)
        curl -fLs \
            "https://www.dropbox.com/scl/fi/b7fenj0wmhzqx64bj82t1/DrivAerNetPlusPlus_CarDesign_Areas.csv?rlkey=usbunuupxwmx6g49r9r7dh8zk&st=xcmc3gm7&dl=1" \
            -o cases/DrivAerNetPlusPlus_CarDesign_Areas.csv

        # Parametric design variables: 4,166 cars × 24 design parameters
        curl -fLs \
            "https://raw.githubusercontent.com/Mohamedelrefaie/DrivAerNet/main/ParametricModels/DrivAerNet_ParametricData.csv" \
            -o cases/DrivAerNet_ParametricData.csv

        # Canonical splits
        for split in train val test; do
            curl -fLs \
                "https://raw.githubusercontent.com/Mohamedelrefaie/DrivAerNet/main/train_val_test_splits/${split}_design_ids.txt" \
                -o "splits/${split}_design_ids.txt"
        done

        echo ">> lite-mode pull complete:"
        ls -la cases/*.csv splits/*.txt

        echo
        echo "NOTE: manifest.json is intentionally NOT built in lite mode —"
        echo "the loader expects an absolute body_length_m, but lite-mode"
        echo "only ships A_Car_Length as a delta. See reference.md for the"
        echo "Stage-09 fix-up options."
        ;;

    full)
        DATAVERSE_BASE="${AERO_DATAVERSE_BASE:-https://dataverse.harvard.edu}"
        DATASET_DOI="${AERO_DRIVAERNET_DOI:?must set AERO_DRIVAERNET_DOI to the Dataverse DOI}"

        # Free-space precondition. Defaults to 1000 GB. The Dataverse sub-
        # datasets are 75 / 213 / 436 / 443 / 10568 GB; the default is too
        # strict for Annotations alone and too loose for two large sub-
        # datasets back-to-back. Operator sets AERO_DRIVAERNET_MIN_FREE_GB
        # to the sum of the targeted sub-datasets + a small margin.
        MIN_FREE_GB="${AERO_DRIVAERNET_MIN_FREE_GB:-1000}"
        FREE_GB=$(df --output=avail -BG /mnt/aero/datasets 2>/dev/null | tail -1 | tr -dc '0-9')
        if [[ -n "${FREE_GB}" && "${FREE_GB}" -lt "${MIN_FREE_GB}" ]]; then
            echo "ERROR: TrueNAS aero/datasets/ has < ${MIN_FREE_GB} GB free (${FREE_GB} GB)." >&2
            echo "       Override threshold via AERO_DRIVAERNET_MIN_FREE_GB if intentional." >&2
            exit 1
        fi

        echo ">> DrivAerNet++ full-mode pull, DOI=${DATASET_DOI}"
        LISTING="$(curl -fsSL \
            "${DATAVERSE_BASE}/api/datasets/:persistentId/?persistentId=${DATASET_DOI}")"
        echo "${LISTING}" | python3 -c "
import json, sys, urllib.request, pathlib
listing = json.load(sys.stdin)
files = listing.get('data', {}).get('latestVersion', {}).get('files', [])
base = '${DATAVERSE_BASE}/api/access/datafile'
for f in files:
    dl = f.get('dataFile', {})
    fid = dl.get('id')
    label = f.get('label') or dl.get('filename')
    if not fid or not label:
        continue
    out = pathlib.Path('cases') / label
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_file() and out.stat().st_size > 0:
        continue
    url = f'{base}/{fid}'
    print(f'>> {label}')
    urllib.request.urlretrieve(url, out)
"

        # Manifest build is currently a no-op for full-mode pulls — the
        # builder is a stub and Stage 09 will revise it once the absolute
        # body-length question is resolved (see reference.md).
        if [[ -f "${REPO_ROOT}/scripts/build_dataset_manifest.py" ]]; then
            python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
                --dataset drivaernet_plus_plus \
                --dataset-dir "${DATASET_DIR}" \
                --out "${DATASET_DIR}/manifest.json" || true
        fi
        ;;

    *)
        echo "ERROR: unknown AERO_DRIVAERNET_MODE='${MODE}' (expected lite|full)" >&2
        exit 2
        ;;
esac

echo ""
echo "Reminder: all artifacts trained on this dataset must carry"
echo "  non_commercial=True in the issued CertificateOfValidity."
