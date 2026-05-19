"""Solver adapters — one subpackage per CFD/ML backend, behind optional extras.

Stage 03 ships only `openfoam`. Each adapter stays concrete and
backend-specific until a second backend (SU2, Stage 06) reveals the right
shared abstraction.
"""

from __future__ import annotations
