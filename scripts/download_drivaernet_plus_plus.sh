#!/usr/bin/env bash
# scripts/download_drivaernet_plus_plus.sh — DrivAerNet++ (CC-BY-NC-4.0).
#
# QUARANTINED dataset (ADR-008 §D4). Gated on three preconditions:
#
#   1. `aero/surrogates/_common/loaders/non_commercial/` tests green.
#   2. `.github/workflows/non-commercial-fence.yml` passing on the PR.
#   3. TrueNAS `aero/datasets/` has ≥ 1 TB free margin on top of the
#      CC-BY-SA sets.
#
# Operator must export `AERO_ACKNOWLEDGE_NONCOMMERCIAL=1` to run this script.
# The acknowledgment is mirrored into MLflow on every training run that
# touches the dataset.
#
# Upstream (Mohamed Elrefaie, MIT): https://dataverse.harvard.edu/dataverse/
# DrivAerNet — Harvard Dataverse, NOT Hugging Face. CC-BY-NC-4.0. Bytes are
# pulled via the Dataverse REST API (no auth needed for download; the dataset
# is publicly readable but bears the non-commercial licence). The GitHub repo
# https://github.com/Mohamedelrefaie/DrivAerNet documents the precise dataset
# DOI under "DOIs for the dataset" in the README; this script reads that DOI
# from the AERO_DRIVAERNET_DOI environment variable so a Stage-09 upgrade can
# pin a specific version without editing the script.

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
DATAVERSE_BASE="${AERO_DATAVERSE_BASE:-https://dataverse.harvard.edu}"
# The DrivAerNet++ Dataverse DOI must be supplied at runtime. The README
# at github.com/Mohamedelrefaie/DrivAerNet lists the canonical DOI under
# the "Dataset Access" section; copy-paste it into the env var.
DATASET_DOI="${AERO_DRIVAERNET_DOI:?must set AERO_DRIVAERNET_DOI to the Dataverse DOI}"

# Free-space precondition. Defaults to 1000 GB — sized for the original
# "single ~800 GB pull" reading of the paper. The Dataverse Native API
# shows the sub-datasets are 75 / 213 / 436 / 443 / 10568 GB; the default
# is too strict for Annotations-only (75 GB) and too loose for two large
# sub-datasets in series. Operator sets AERO_DRIVAERNET_MIN_FREE_GB to
# the sum of the targeted sub-datasets + a small margin.
MIN_FREE_GB="${AERO_DRIVAERNET_MIN_FREE_GB:-1000}"
FREE_GB=$(df --output=avail -BG /mnt/aero/datasets 2>/dev/null | tail -1 | tr -dc '0-9')
if [[ -n "${FREE_GB}" && "${FREE_GB}" -lt "${MIN_FREE_GB}" ]]; then
    echo "ERROR: TrueNAS aero/datasets/ has < ${MIN_FREE_GB} GB free (${FREE_GB} GB)." >&2
    echo "       Override threshold via AERO_DRIVAERNET_MIN_FREE_GB if intentional." >&2
    exit 1
fi

mkdir -p "${DATASET_DIR}/cases"
cd "${DATASET_DIR}"

# 1. List all files in the Dataverse dataset using the Native API. No
#    auth is required for public datasets.
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

# 2. Build the manifest the aero loader consumes. Same caveat as the
#    CC-BY-SA loaders — the upstream CSV column names need to be mapped
#    onto the aero schema; the dedicated post-processor lives in
#    `scripts/build_dataset_manifest.py --dataset drivaernet_plus_plus`.
python3 "${REPO_ROOT}/scripts/build_dataset_manifest.py" \
    --dataset drivaernet_plus_plus \
    --dataset-dir "${DATASET_DIR}" \
    --out "${DATASET_DIR}/manifest.json"

dvc add manifest.json cases/
dvc push -r aero-minio

echo "DrivAerNet++ mirror complete; manifest + cases registered under DVC."
echo "Reminder: all artifacts trained on this dataset must carry"
echo "  non_commercial=True in the issued CertificateOfValidity."
