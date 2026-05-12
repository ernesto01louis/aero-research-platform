#!/usr/bin/env bash
# Push CFD case templates + the aero_research_platform Python package to
# a deploy target via SSH+rsync.
#
# Usage: scripts/push_templates.sh <target-name>
# Example: scripts/push_templates.sh aero-research
#
# Assumes the orchestrator's config.json has the target wired (Stage 2)
# and that the per-target SSH key is at /root/.ssh/id_ed25519_<target>_target.
#
# Why this exists: the orchestrator's planner/generator agents only know
# how to write a bash run.sh. The CFD case (15+ small files) is too much
# to inline into prompts. So we stage it on the target once, then the
# orchestrator-generated run.sh just `cp -r ~/templates/...` into the run
# directory.

set -euo pipefail

TARGET="${1:?usage: push_templates.sh <target-name>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Look up host + user from config.json (Stage 2 wired this).
HOST="$(python3 -c "
import json, sys
cfg = json.load(open('/opt/ai-orchestrator/config.json'))
for t in cfg.get('ssh_targets', []):
    if t['name'] == '${TARGET}':
        print(t['host']); break
" )"
USER="$(python3 -c "
import json, sys
cfg = json.load(open('/opt/ai-orchestrator/config.json'))
for t in cfg.get('ssh_targets', []):
    if t['name'] == '${TARGET}':
        print(t['username']); break
" )"
KEY="$(python3 -c "
import json, sys
cfg = json.load(open('/opt/ai-orchestrator/config.json'))
for t in cfg.get('ssh_targets', []):
    if t['name'] == '${TARGET}':
        print(t['key_path']); break
" )"

if [[ -z "${HOST}" || -z "${USER}" ]]; then
    echo "ERROR: target '${TARGET}' not found in /opt/ai-orchestrator/config.json"
    exit 2
fi

SSH_OPT=(-i "${KEY}" -o StrictHostKeyChecking=no -o BatchMode=yes)

echo "Pushing templates to ${USER}@${HOST}:~/templates/"
ssh "${SSH_OPT[@]}" "${USER}@${HOST}" "mkdir -p ~/templates ~/aero-research-platform"

# Case templates -> ~/templates/
rsync -avz --delete -e "ssh ${SSH_OPT[*]}" \
    "${REPO_ROOT}/cfd/templates/" \
    "${USER}@${HOST}:~/templates/"

# Python package -> ~/aero-research-platform/ (so generate_mesh.py can import it)
rsync -avz --delete -e "ssh ${SSH_OPT[*]}" \
    --exclude "__pycache__" \
    --exclude ".mypy_cache" \
    --exclude ".pytest_cache" \
    --exclude ".ruff_cache" \
    --exclude ".git" \
    --exclude "data" \
    --exclude "results" \
    --exclude "notebooks" \
    "${REPO_ROOT}/aero_research_platform" \
    "${USER}@${HOST}:~/aero-research-platform/"

# Also push pyproject.toml so the user can `pip install -e .` for SDK pluggy.
rsync -avz -e "ssh ${SSH_OPT[*]}" \
    "${REPO_ROOT}/pyproject.toml" \
    "${REPO_ROOT}/README.md" \
    "${USER}@${HOST}:~/aero-research-platform/"

# Scripts (preamble.sh + pull) — the LLM-generated run.sh sources
# preamble.sh from /home/${USER}/aero-research-platform/scripts/, so
# this rsync IS load-bearing for every run.
ssh "${SSH_OPT[@]}" "${USER}@${HOST}" "mkdir -p ~/aero-research-platform/scripts"
rsync -avz -e "ssh ${SSH_OPT[*]}" \
    "${REPO_ROOT}/scripts/preamble.sh" \
    "${USER}@${HOST}:~/aero-research-platform/scripts/"
ssh "${SSH_OPT[@]}" "${USER}@${HOST}" "chmod +x ~/aero-research-platform/scripts/preamble.sh"

echo "Done. Remote listings:"
ssh "${SSH_OPT[@]}" "${USER}@${HOST}" "ls -la ~/templates/ && echo --- && ls -la ~/aero-research-platform/aero_research_platform/"
