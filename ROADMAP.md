# ROADMAP

## Phase 0 — Bootstrap (Stage 3)

**Status: DONE.** This is the work in this very repo's initial four commits.

- [x] Public repo on GitHub, Apache-2.0, branch protection on `main`.
- [x] `pyproject.toml` with SDK pin + pluggy evidence entry points.
- [x] Namespace package `aero_research_platform/` with stub submodules.
- [x] Three Phase-1 campaign YAMLs committed verbatim from the brief.
- [x] CI: pytest + ruff + mypy on push/PR.
- [x] Smoke tests prove the consumer contract — every YAML round-trips through `ai_orchestrator_client.CampaignCreate`.

## Phase 1 — First three campaigns

### 1.1 NACA 0012 baseline validation (`campaigns/01-naca0012-baseline.yaml`)

- [ ] Implement `aero_research_platform/meshing/airfoil_cmesh.py` — NASA-TMR-grade C-grid generator (897 × 257 cells, farfield ≈ 500 c).
- [ ] Implement `aero_research_platform/cfd/templates/simpleFoam_k_omega_sst/` — OpenFOAM v2412 case template (M=0.15, Re=6e6, low-Re wall function).
- [ ] Implement `aero_research_platform/cfd/post.py` — read `postProcessing/forceCoeffs1/coefficient.dat`, return Cl, Cd, y+ surface stats.
- [ ] Run α ∈ {0°, 10°}; verify Cl within ±2% and Cd within ±10% of NASA TMR reference.
- [ ] Promote `aero_research_platform/evidence/aero_metrics.py` from stub: report per-α deltas vs hypothesis bounds.

### 1.2 Bechert 1997 blade-riblet replication (`campaigns/02-flat-plate-riblet-bechert.yaml`)

- [ ] Implement `aero_research_platform/geometry/riblet.py` — blade-riblet cross-section (h/s=0.5, t/s=0.02).
- [ ] Implement `aero_research_platform/meshing/periodic_riblet_strip.py` — periodic flat-plate strip, riblet bottom wall, ≥16 cells/pitch.
- [ ] Sweep s⁺ ∈ {5, 10, 15, 17, 20, 25, 30, 35, 40}; compute DR% vs smooth baseline at matched Re_θ.
- [ ] Verify peak DR within ±2 pp at s⁺ ≈ 17; crossover s⁺ ≈ 27 ± 3.
- [ ] Promote `aero_research_platform/evidence/riblet_drag_reduction.py` from stub: compute the DR-vs-s⁺ curve and check Bechert 1997 Figure 5 alignment.
- [ ] Escalation path: wall-resolved LES on SkyPilot A100 burst (per Mele & Tognaccini 2022) if RANS misses.

### 1.3 NACA 0012 + static riblet sweep (`campaigns/03-naca0012-riblet-sweep.yaml`)

- [ ] Compose Phase 1.1 mesher + Phase 1.2 riblet generator → riblet patch on NACA 0012 suction surface (x/c ∈ [0.10, 0.90]).
- [ ] Sweep target s⁺ ∈ {10, 12, 14, 16, 18, 20, 22, 25}; baseline at every s⁺ for self-consistent DR.
- [ ] Verify peak DR in the 3–10% credible band (per MicroTau / NTRS 19880005573 framing).
- [ ] Flag for re-examination of mesh resolution near riblet tips when outside band (per Bechert 1997 tip-sharpness warning).

## Phase 2 — Surrogate acceleration

(Outline only; lands after Phase 1 closes.)

- FNO airfoil surrogate (`surrogates/fno_airfoil.py`) trained on Phase 1.1 + 1.3 data.
- MeshGraphNet surrogate (`surrogates/meshgraphnet.py`) for the riblet sweep.
- Train on SkyPilot A100 bursts (`sky/train-fno.yaml`, `sky/train-mgn.yaml`).
- `train.py` driver.

## Phase 3 — Middle-loop optimization

- PPO env (`optimization/ppo_riblet_env.py`) that proposes (h/s, t/s, target s⁺) and queries the surrogate for reward.
- NSGA-II driver (`optimization/nsga2_riblet.py`) for multi-objective DR-vs-CL.

## Phase 4 — Outer-loop hypothesis generation

- `llm/hypothesis_prompts.py` — Jinja templates consumed by the orchestrator's planner agent.
- The planner reads prior campaigns' evidence bundles + reference notes (NoteDiscovery) and proposes the next `CampaignCreate`.
