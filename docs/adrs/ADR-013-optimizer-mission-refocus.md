# ADR-013 — Optimizer-mission refocus (aerodynamic shape optimizer; flapping flagship)

- **Status:** accepted
- **Date:** 2026-06-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 09)
- **Stage:** 09
- **Supersedes:** the original-brief scope where it conflicts (not an ADR — see
  `docs/handoff-bundle/archive/00-CONTEXT-project-brief.md`); re-points the surrogate
  destination of ADR-010

## Context and problem statement

The platform was built (Stages 01–09) against a generic "do-everything" brief whose ML
half pointed at a fixed automotive surrogate zoo (DoMINO/Transolver/FIGConvNet/X-MGN +
MoE on DrivAerML) and whose V&V pointed at transport-aircraft workshops (DPW-7/HLPW-5).
The operator delivered two documents — a mission/scope refocus
(`docs/handoff-bundle/00-MISSION-AND-SCOPE.md`) and an architecture briefing
(`docs/architecture/BRIEFING-architecture-review-for-independent-challenge.md`) — and
then a decisive correction that names the actual mission:

**The platform is a hypothesis-driven aerodynamic shape/topology optimizer** — geometry
in, CFD-verified improved geometry out, CFD as ground truth. The forward CFD + UQ +
provenance stack is the *foundation that makes claimed improvements trustworthy*, not
the deliverable. **Flapping-wing is the single flagship demonstration domain** (broad +
underexplored). **Riblets demote to one example** (an earlier draft wrongly elevated
them to a co-flagship). The **optimization loop is the mission and a named milestone**,
not post-v0.1.0 backlog.

This ADR records the refocus, its honest basis, and its consequences (including the
artifacts the cut strands and a cancelled paid training run). The mission detail lives
in the governing scope doc; the re-aimed Stage 10–20 map in
`docs/handoff-bundle/README-handoff.md`.

## Decision drivers

- **Name the mission.** "Surrogate zoo" and "two flagships" both obscured that the
  *optimizer* is the product. The optimization loop must be a first-class, sequenced
  milestone.
- **Scientific fit.** Flapping-wing is broad and underexplored — where a rigorous
  optimizer adds new, validated knowledge. Riblets are narrow and already answered.
- **Honesty about ML transfer.** Cross-domain neural-operator transfer
  (automotive→airfoil) is *unresolved* in the 2023–2026 literature — no published
  evidence it helps or hurts. So the automotive zoo cannot be justified for a bio/wing
  optimizer, and the own-data surrogate factory sidesteps the question entirely.
- **"Do NOT start over."** Stages 1–8 (provenance, conventions, five solver adapters,
  the surrogate framework) are the expensive, correct, mission-agnostic core.
- **General architecture, mission-first prioritization.** Keep the `Solver`/`Surrogate`
  protocols and capability-layer generality (the briefing's framing); prioritize effort
  on the optimizer + flapping. SCOPE-GATE gates effort, not interface generality.

## Considered options

1. **Continue the original roadmap** (automotive zoo + DPW/HLPW; status quo).
2. **Full restart** on the optimizer mission (discard Stages 1–8).
3. **Refocus keeping Stages 1–8 + general interfaces, optimizer-mission-first** — chosen.

## Decision outcome

Chose **Option 3** because it preserves the correct, expensive foundation while
re-aiming everything from Stage 10 around the optimizer and the flapping flagship.

### Keeps / promotions

- **Core, untouched:** the four-tuple provenance backbone (DVC/MLflow/Postgres), the
  conventions, the walking-skeleton discipline, the `Solver`/`Surrogate` protocols, the
  `CertificateOfValidity` framework.
- **Core:** OpenFOAM-ESI (forward workhorse + moving mesh, v2412); **the optimization
  loop** (the mission); the **surrogate framework repurposed for an own-data factory**
  that accelerates the optimizer; **arbitrary-geometry ingestion + robust meshing** (a
  committed milestone); preCICE+CalculiX FSI (flexible flapping, later).
- **Frozen-optional (kept, not deleted):** **SU2** (re-motivated as the adjoint seed for
  the post-v0.1.0 gradient/topology layer, with DAFoam v5), PyFR, NekRS, JAX-Fluids.

### Cuts

- **DoMINO/Transolver/FIGConvNet/X-MGN-on-DrivAerML as designed** and the **MoE gate** —
  wrong fuel (car shapes) for a wing optimizer; transfer unproven; the own-data factory
  replaces them.
- **DPW-7 / HLPW-5** V&V — transport-aircraft cruise; replaced by the flapping ladder.
  **NASA TMR kept** as the general turbulence-model baseline.
- **Riblet / channel-DNS roadmap stages** — riblets demote to an example (governing
  scope doc §A).
- **Deferred indefinitely:** the NeMo Agent Toolkit / AI-Q fork and the literature miner.

### Consequences

- **Positive:** the mission is named and sequenced; the first thesis-grade result (a
  CFD-verified flapping optimization delta) is a milestone (Stage 15), not backlog; the
  fleet narrows to what the mission needs; the surrogate framework is reused as-is for
  own data.
- **Negative — cancelled spend + stranded artifacts (frozen, NOT deleted):** the
  Stage-09 Phase-3 DoMINO training is **CANCELLED** ($67–191 of H100 avoided). The cut
  strands real built artifacts that are **frozen in place, never deleted** (Hard Rule 5
  / propose-first governs any removal): `aero/surrogates/domino/`,
  `scripts/stage09_domino_train.py`, `docs/runbooks/stage-09-phase-3-domino-training.md`,
  the signed 15 GB `physicsnemo.sif`, and the **484-run / ~353 GiB DrivAerML** subset on
  the `aero-nfs` DVC remote. **DrivAerML disk reclaim is a separate propose-first
  decision requiring literal `approved`** (TrueNAS has ~369 GB free — real pressure, not
  this session's call); ledgered as a follow-up.
- **Neutral / followup:** budget envelope → **ADR-014**; FSI structural-solver strategy →
  **ADR-016**; six new rules adopted (two promoted to the Constitution via **ADR-015**,
  72 h review); the old Stage 10–16 map is superseded by the 10–20 map; `00-CONTEXT` and
  the original prompts are archived under `docs/handoff-bundle/archive/`.

## Pros and cons of considered options

### Option 1 — continue the original roadmap
- Good: zero churn; the DoMINO Phase-3 work would land a trained model.
- Bad: trains on the wrong data for the mission; spends $67–191 on a path being cut;
  leaves the optimizer (the actual product) as indefinite backlog.

### Option 2 — full restart
- Good: a clean optimizer-first repo with no frozen baggage.
- Bad: discards the correct, expensive Stages 1–8 (provenance, protocols, five adapters);
  directly violates the operator's "do NOT start over."

### Option 3 — refocus, keep foundation (chosen)
- Good: preserves the foundation; re-aims cheaply (Stages 09–16 were mostly prompts); the
  surrogate framework + protocols are already general, so the own-data factory is cheap.
- Bad: carries frozen artifacts (disk + maintenance surface) until reclaimed; the
  refocus touches many governance files in one pass.

## Links

- Governing scope: `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` (revised)
- Architecture input: `docs/architecture/BRIEFING-architecture-review-for-independent-challenge.md`
- Stage map: `docs/handoff-bundle/README-handoff.md`
- Related ADR: ADR-007 (budget cap value → ADR-014), ADR-008/009 (surrogate framework +
  taint, reused), ADR-010 (DoMINO surrogate, destination re-pointed), ADR-015
  (constitution invariants 10–11), ADR-016 (FSI structural solver)
- Related handoff: `docs/handoffs/STAGE-09-domino-baseline-surrogate-DONE-2026-06-01.md` §13
- External: Luo, Kasirzadeh & Shah, arXiv:2509.08713 (AI-scientist failure modes);
  AirfRANS (Bonnet et al., NeurIPS 2022); GINO (Li et al., NeurIPS 2023)
