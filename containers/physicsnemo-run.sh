#!/usr/bin/env bash
# containers/physicsnemo-run.sh — how to run the PhysicsNeMo DoMINO image.
#
# --shm-size=1g is MANDATORY for PhysicsNeMo's data loaders (they use shared
# memory for tensor batches). It manifests differently per runtime:
#
#   * RunPod / Docker (the pod IS the physicsnemo container):
#       docker run --gpus all --shm-size=1g <image> \
#         python scripts/stage09_domino_train.py --config conf/surrogate/domino.yaml
#     If a job dies with a DataLoader "bus error", the shm size is the first
#     suspect. RunPodExecutor must set the pod shm to >= 1 GB (Stage 09 op step).
#
#   * Apptainer on an aero LXC (local-GPU dry-run / break-glass):
#       apptainer exec --nv /opt/aero/containers/physicsnemo.sif \
#         python scripts/stage09_domino_train.py --config conf/surrogate/domino.yaml
#     Apptainer shares the host /dev/shm directly (no --shm-size flag); ensure
#     the host /dev/shm is >= 1 GB.
#
# This wrapper is the apptainer convenience form; override the SIF path with
# AERO_PHYSICSNEMO_SIF.

set -euo pipefail
SIF="${AERO_PHYSICSNEMO_SIF:-/opt/aero/containers/physicsnemo.sif}"
exec apptainer exec --nv "${SIF}" "$@"
