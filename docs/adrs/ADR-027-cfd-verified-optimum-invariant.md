# ADR-027 — Constitutional promotion of Hard Rule 14 (CFD-VERIFIED-OPTIMUM-ONLY) → Invariant 12

- **Status:** proposed (carries a CONSTITUTION amendment — separate micro-PR, ≥72 h window per the
  ADR-015 amendment process)
- **Date:** 2026-07-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 15)
- **Stage:** 15 (the scheduled promotion point — where `OptimizationResult` lands in a real loop)
- **Supersedes:** none (promotes CLAUDE.md Hard Rule 14 to a Constitution Invariant)

## Context

CLAUDE.md Hard Rule 14 — **CFD-VERIFIED-OPTIMUM-ONLY** — has always scheduled its constitutional
promotion "at Stage 15 when the `OptimizationResult` schema lands [in a real loop]" (ADR-013). Stage
15 built the direct-CFD Bayesian optimizer (`aero/optimize/`, ADR-026) and produced the first
CFD-verified improvement, so the rule is now load-bearing in shipped, CI-gated code — the trigger to
promote it from a Hard Rule to a numbered CONSTITUTION Invariant, alongside Invariant 10
(IMPROVEMENT-EXCEEDS-UNCERTAINTY) and Invariant 11 (NO-SURROGATE-ON-FOREIGN-DATA).

## Decision

Add **CONSTITUTION Invariant 12 — CFD-VERIFIED-OPTIMUM-ONLY**:

> Every reported optimum is verified by a ground-truth CFD run before it is reported; no optimum is
> claimed on a surrogate prediction alone. Best-of-N reporting is selection-bias-aware: the reported
> optimum is verified on a **held-out** CFD evaluation not seen by the optimizer, and the pool size
> N (`n_candidates`) is recorded. **Enforcement:** `aero/vv/reportable.py::OptimizationResult`
> carries the four-fold provenance of the verifying ground-truth CFD run (`cfd_verified`) and
> refuses to construct a best-of-N result (`n_candidates > 1`) without `held_out_verification`;
> `aero/optimize` evaluates every candidate by direct CFD (ADR-026). Guards the documented
> AI-scientist failure modes (Luo, Kasirzadeh & Shah, arXiv:2509.08713: post-hoc selection bias,
> metric misuse, data leakage).

The amendment observes the full ≥72 h review window (ADR-015 proposed→accepted lifecycle) and merges
on operator approval — a **parallel micro-PR** touching only `CONSTITUTION.md` (this ADR + the code
land without waiting; the schema already enforces the rule).

## Decision drivers

- **The schema already enforces it.** `OptimizationResult`'s `cfd_verified` four-tuple + the
  `n_candidates > 1 ⇒ held_out_verification` validator make a non-verified or selection-biased
  optimum *unconstructible* — the Invariant-11 "unconstructible invalid state" precedent.
- **It is now shipped + used** (Stage-15 optimizer), so it belongs in the Constitution, not only in
  CLAUDE.md's Hard Rules.
- **Pairs with Invariant 10.** A thesis-grade optimization result needs both the improvement to
  exceed its uncertainty (Inv 10) AND the optimum to be CFD-verified + selection-bias-aware (Inv 12).

## Consequences

- **Positive:** the optimizer's core integrity guarantee is constitutionally enshrined + CI-gated;
  the platform's "trustworthy improvement" product bar is complete (Inv 10 + 11 + 12).
- **Process:** the CONSTITUTION.md text changes → the ≥72 h amendment window applies (ADR-015). The
  ADR + code do not wait; the Constitution micro-PR merges on window + operator approval.

## Links

- Promotes CLAUDE.md Hard Rule 14; realises the ADR-013 schedule. Related: ADR-015 (Inv 10/11
  promotion + the amendment process), ADR-023 (Inv 10 measured u95_delta), ADR-026 (the optimizer).
- `aero/vv/reportable.py::OptimizationResult`, `.claude/rules/optimization-integrity.md`.
