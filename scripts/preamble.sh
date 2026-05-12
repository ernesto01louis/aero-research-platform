#!/usr/bin/env bash
# Preamble for orchestrator-generated run.sh scripts targeting the
# aero-research LXC. Source this BEFORE any python/openfoam command.
#
# Why: Stage-2 deviation #5 — orchestrator's environment_inspector calls
# pip list against system Python on the target, not /opt/aero-venv. Tools
# that resolve binaries by PATH or rely on the activated venv must source
# both the venv and the OpenFOAM environment.
#
# Idempotent — safe to source multiple times in a single shell.

# Python venv.
if [[ -f /opt/aero-venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source /opt/aero-venv/bin/activate
fi

# OpenFOAM v2412 environment from ESI Debian package.
if [[ -f /usr/lib/openfoam/openfoam2412/etc/bashrc ]]; then
    # shellcheck disable=SC1091
    source /usr/lib/openfoam/openfoam2412/etc/bashrc
elif [[ -f /opt/openfoam2412/etc/bashrc ]]; then
    # shellcheck disable=SC1091
    source /opt/openfoam2412/etc/bashrc
fi

# Make our Python package importable for generate_mesh.py.
export PYTHONPATH="${HOME}/aero-research-platform:${PYTHONPATH:-}"
