# STAGE NN — Rigid-Flapping Optimization (after the foundation, ADR-051)

> **Held until the foundation is built (ADR-051).** This prompt was drafted at Stage 21 as the first
> post-v0.1.0 stage. ADR-051 moved it behind the five foundation stages (22–26):
> - an honest V&V report;
> - provenance you can trust;
> - running the registry;
> - the turbulent canonical cases;
> - forward-model validation for the optimization targets.
>
> It gets its stage number, `NN`, when Stage 26 closes. Before it is used, update it from Stage 26's
> result. In particular, the claim bound in D1.4 is set from Stage 26's flapping validation, not
> from Stage 14's 45.7 % miss alone. Every "Stage 22" below means this stage.

> **v0.1.0 is released, and Stage 21 is CLOSED.** The release-first stage (ADR-046) shipped:
> - the result crates (Invariant 13, ADR-047);
> - the dependency licence scan (Invariant 5, ADR-048);
> - the release governance (ADR-049);
> - JOSS-ready metadata.
>
> **The limitation v0.1.0 carried is this stage's starting point.** At v0.1.0 the optimizer was
> demonstrated on the **airfoil** case only. **The optimizer had never been run on a flapping-wing
> case, and v0.1.0 made no flapping-wing optimization claim.** This stage runs the optimizer over
> Stage 14's **rigid, prescribed-kinematics** flapping capability, for the first time.
>
> **Flexible-flapping optimization stays DEFERRED** (ADR-046 S4). Re-entry needs ADR-046 S5 and a
> NEW ADR. Stage 20 stays closed: never retry one of its levers, and never fill a B-sentinel.
>
> **No solve before two ADRs, both accepted by the operator:**
> 1. the pre-registration ADR (D1 below);
> 2. the compute-campaign ADR (D2), which fixes the budget tier.

## BEFORE YOU START — READ

- `CLAUDE.md`, now with Invariant 13 and the release-tag rule; `.aero-stage` (set it to NN in
  the first commit).
- `docs/handoffs/STAGE-21-release-portable-bundles-DONE-*.md`: the release record, the gotchas
  and the ledger pointers.
- The Stage-14 record:
  - `docs/handoffs/STAGE-14-rigid-flapping-wing-DONE-2026-07-10.md` (headline, §3, and the
    confidence note: wake capture is "the leading hypothesis");
  - `docs/vv/stage14-preregistration.md`;
  - `data/vv/stage14_flapping_nogo.json`;
  - `crates/stage14-rigid-flapping-wbd2004/`.
- The capability:
  - `aero/vv/flapping/wbd2004.py` (WBD 2004 idealised kinematics: pitch mean 90°, pitch
    amplitude 45°, stroke A0/c = 2.8, Re = 75; rotation timing via the pitch phase
    φ = +45 / 0 / −45°);
  - `aero/adapters/openfoam/flapping_wing.py` and `motion.py`;
  - the overset path (ADR-024).
- The optimizer and the claim machinery:
  - `aero/optimize/` (`bo.py`, `objective.py`, `report.py`, `accelerated.py`);
  - `aero/vv/reportable.py`, `reportable_compose.py` (`compose_improvement`) and
    `paired_difference.py`;
  - `.claude/rules/optimization-integrity.md`.
- The producer contract for results: ADR-047. Keep the exact `resolved_config` passed to
  `compute_provenance`, and export through `aero.crate.write_crate`. No era recipes are needed
  from now on.
- `docs/operator/deferred-work-ledger.md`, the section "Rigid-flapping optimization — pre-registration items
  carried from Stage 21", which holds the per-evaluation retry item (D1.6).

## Why this stage

The mission's own publication bar (`00-MISSION-AND-SCOPE.md` §5) asks for a CFD-verified
optimization delta on a **flapping** case that exceeds its combined U95. v0.1.0 does not meet it.
Two things block an honest attempt with flexible FSI:
- the flexible stack's NO-GO on infrastructure (Stage 20);
- the missing experiment anchor on rigid mean lift (Stage 14's 45.7 % miss).

Rigid prescribed kinematics are cheap enough to optimize. Stage 14 showed they reproduce the
rotation-timing *ordering*. What they do not reproduce is the absolute *mean lift*. That shapes
every claim this stage may make: **deltas, not absolutes**.

## Deliverables

### 1. Bookkeeping (first commit)

- `.aero-stage` → NN.
- The Dependabot commit prefix → `ci(stage-NN)`. The workflow-hygiene test enforces it.
- A `status: partial` Stage-22 handoff from the first commit on, with `stage_tag: v0.2.0`, or
  whatever version the operator chooses at open.

### 2. D1 — the pre-registration ADR, accepted before any solve

It fixes:
1. **The design space.** At most 3 variables, each **inside the regime where the Stage-14
   ordering held**. For example: the pitch phase φ ∈ [−45°, +45°], the pitch amplitude β around
   45°, and optionally the pitch mean α0. Everything else is held at the WBD kinematics, Re 75
   and the Stage-14 numerics.
2. **The objective and the baseline.** For example, stroke-averaged mean lift, or a
   lift-per-power figure, at **matched conditions** against the symmetrical WBD baseline (same
   mesh topology, numerics and cycle window).
3. **The U95 of the delta**, composed with `compose_improvement`:
   - the **paired** statistical term: NOBM plus τ_int on the per-cycle *difference* series;
     cancellation is measured, not assumed (ADR-023);
   - the GCI on the delta;
   - an input or model-form term.

   With k = 2. `HandEnteredDeltaU95` is not allowed for the claim.
4. **The claim bound, derived from Stage 14's misses** (45.7 % symmetrical, 38 % advanced,
   64 % delayed against experiment):
   - only matched-condition **deltas** are claimed, never absolute coefficients;
   - a written **bias-bound statement** says what an unanchored forward model can and cannot
     support;
   - the tier is **capped at `validated`** while the flapping forward model has no passing
     experiment anchor.
5. **The gates and the stopping rule:**
   - the convergence and steadiness gates (periodic steady state; the ADR-019 cumulative bound,
     discard-first);
   - the evaluation budget;
   - the held-out verification design (Hard Rule 14; best-of-N with `n_candidates` recorded).
6. **The per-evaluation crash-tolerance policy** (carried from Stage 21, external review item C).
   - **Today:** a failed solve is skipped and still counts against the budget (the Stage-17
     pre-registered gate S8).
   - **To pre-register:**
     - a **bounded retry for transport failures only** (the Executor's `transport_error`),
       never for a deterministic divergence;
     - whether **every attempt counts as a spent evaluation**;
     - **the failure signature persisted** in the iteration evidence.
   - **Boundary:** this is NOT coupled-FSI restart (ADR-045 A19 / ADR-046 S5).

### 3. D2 — the compute-campaign ADR, approved by the operator before any run

It covers the budget tier (sustained or burst), the wall-time estimate from Stage-14 timings, the
cost cap (Invariant 8), and the `run_long.sh` reap and timeout plan.

### 4. The campaign

- Direct-CFD Bayesian optimization (`aero/optimize/bo.py`) over D1's space.
- Every evaluation produces a four-fold provenance tuple.
- The CFD-verified **held-out** optimum is a fresh solve, not a loop re-read. Its delta and U95
  come from `compose_improvement`.

### 5. The result crate

Export with `aero.crate.write_crate`, following the producer contract. The crate must round-trip
in `crate round-trip — Invariant 13`. Add it to the committed crates and to the oracle
(`scripts/crate_oracle.py`, `DIGESTS`) in the same PR.

### 6. Optional (operator's choice at stage open)

Implement ADR-050, the hosted CPU-only reproducible CFD number. Otherwise it waits for a v0.1.x
patch.

## GO / NO-GO

- **GO** requires all of these:
  - a CFD-verified, held-out optimum whose matched-condition delta exceeds 2·U95 under the
    pre-registered composition;
  - every pre-registered gate passed;
  - the crate exported, and round-tripping.

  The claim is a **delta** at most `validated`, with the bias-bound statement carried in the crate.
- **NO-GO** is the honest outcome when any gate fails. Document it, keep the evidence, and never
  relax a pre-registered band.

## Infra, conventions and inherited notes

- **CI and merging:**
  - The required contexts (12) are in `.github/required-checks.json`.
  - Branch protection is strict: one merge per main movement.
  - Squash merges break stacked branches: after a base merges, merge `main` into the next branch
    and take main's copy of the files the base introduced.
  - Never push while a self-hosted job on that branch is in progress, and never cancel one.
  - Check that every commit header is ≤ 100 characters **before** pushing.
- **The V&V report is not ALL GREEN.** The turbulent TMR flat plate has failed Cf since Stage 5,
  so no run may be tagged `production`.
- **Long jobs** go through `scripts/run_long.sh`, with REAP on. Never use `run_long.sh wait`.
- **Hard don'ts** (unchanged):
  - never create the two ADR-045 records;
  - never fill a B-sentinel;
  - keep `stage-20-evidence-2026-09-20`;
  - never write a crate under `data/vv/`.
- **JOSS** is the operator's. Only the operator replies to editors and reviewers; an agent
  session never drafts, posts or edits a review comment (`docs/release/joss.md`).

## POST-STAGE HANDOFF (mandatory)

One file, kept from the first commit to the close. Emphasise:
- the D1/D2 ADRs, and what the gates decided;
- the delta, its U95 composition and the measured cancellation (`variance_reduction`);
- the bias-bound statement;
- the crate digest;
- what the next stage (or the S5 re-entry) needs.

Author the next stage's prompt before closing.
