# ADR-014 — Budget envelope revision (tiered cap; per-stage expectations)

- **Status:** accepted
- **Date:** 2026-06-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 09)
- **Stage:** 09
- **Supersedes:** the cap-*value* policy of ADR-007 (not its mechanism)

## Context and problem statement

ADR-007 set a flat **$50/month** cloud-GPU cap (`AERO_RUNPOD_MONTHLY_CAP_USD`, enforced
by `CostCap` per CONSTITUTION Invariant 8). The operator notes that $50 was an arbitrary
placeholder and is open to a recommended envelope "well under five figures." The
optimizer mission (ADR-013) makes the heavy work the **optimization loop** (many forward
CFD solves per optimization) and **surrogate training** — which $50 will not cover. The
cap *mechanism* (ledger, pre-launch check, orphan-refusal, Invariant 8) is sound and
stays; only the *ceiling value* and the per-stage expectation change.

## Decision drivers

- **Realism for the mission.** A Bayesian-opt loop is tens-to-low-hundreds of CFD
  evaluations; surrogate training is GPU-hours.
- **Most forward work is on-prem-CPU.** Low-Re unsteady flapping CFD is frequently
  tractable on the Proxmox homelab — the cost driver is the *count* of solves
  (optimization) and GPU work (surrogate / 3D-unsteady / FSI), not individual solves.
- **Keep the cap honest.** Tiers must be explicit and per-campaign-approved, not a blank
  cheque; the Invariant-8 fail-loud overrun behaviour is unchanged.

## Considered options

1. **Tiered envelope** (baseline default + sustained + burst tiers) — chosen.
2. **One higher flat cap** (e.g. $300/mo) — simpler, but blurs routine vs campaign spend.
3. **Keep $50** and raise per-run as needed — status quo; forces a manual raise for every
   campaign and obscures the real monthly envelope.

## Decision outcome

Chose **Option 1.** Adopt the briefing's tiers:

| Tier | Envelope | Mechanism | Typical stages |
|---|---|---|---|
| **Baseline** | **$150/mo** (new `AERO_RUNPOD_MONTHLY_CAP_USD` default) | the standing cap | Stages 10–14 (V&V, moving-mesh dev, UQ, transition, rigid-flapping validation — mostly on-prem CPU + light cloud) |
| **Sustained campaign** | $200–600/mo | per-campaign env-var override, recorded in the stage prompt + handoff | Stage 15 (optimization loop), Stage 16 (surrogate training) |
| **Burst month** | $1–2k | explicit per-run `approved` + ledger annotation (the existing Stage-09 per-run-raise flow) | large surrogate / FSI / flexible-flapping campaigns (Stages 18–20) |

### Key decisions
- The **code default** in `aero/orchestration/cost_cap.py` bumps `$50 → $150` (Stage 10,
  with a one-line test update). No change to the ledger schema, the pre-launch check, the
  orphan-refusal, or Invariant 8 wording ("the configured ceiling").
- Sustained/burst tiers are **per-campaign overrides**, named in the owning stage prompt
  and recorded in the handoff — never silent.
- Total annual spend stays comfortably under five figures.

## Consequences

- **Positive:** routine months are covered without per-run raises; campaign spend is an
  explicit, ledgered decision; the mechanism is untouched.
- **Negative:** the higher baseline is a larger standing exposure than $50 (mitigated by
  the unchanged fail-loud overrun + orphan refusal).
- **Neutral / followup:** GPU pricing is volatile (briefing §9, [VERIFY]); re-check live
  rates before any sustained/burst campaign. Stage 13's multi-cloud router (deferred)
  will honour the same tiers.

## Links

- Related ADR: ADR-007 (cost-cap mechanism; cap *value* superseded here), ADR-013
  (mission refocus that motivates the tiers)
- Code: `aero/orchestration/cost_cap.py`, `tests/stage_07/test_cost_cap.py`
- CONSTITUTION Invariant 8 (unchanged)
