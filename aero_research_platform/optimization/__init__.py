"""RL (Stable-Baselines3) and evolutionary (pymoo) optimization (stub).

Middle-loop search in the three-loop architecture (see VISION.md).
Stage 4+ lands ``ppo_riblet_env.py`` (gymnasium env that proposes
riblet (h/s, t/s, target s+) and queries the surrogate for reward)
and ``nsga2_riblet.py`` (multi-objective DR%-vs-CL search).
"""
from __future__ import annotations

__all__: list[str] = []
