# Technical Review — `aero-research-platform`

**Reviewed at:** `v0.0.12` (Stage 12 complete, commit `cbfc75a` / PR #23), main branch.
**Scope of review:** full package read of `aero/` (101 modules, ~16k LoC), the governing
docs (mission/scope, Constitution, 20-stage map, ADR references), the Stage 01–12 handoff
notes, and the test suite (ran 317 host-side tests green; the ~20 that need Postgres/cluster
were not run). Emphasis was placed on the scientific core (UQ, V&V, provenance), because that
is where the project's thesis lives and therefore where a defect is most expensive.

**One-line verdict:** This is exceptional solo research engineering — the discipline is
genuinely rare. The risks are not in what's built; they're concentrated in (a) one hollow spot
at the *center* of the already-shipped integrity guarantee, (b) a known physics discrepancy
sitting directly upstream of the flagship, and (c) the fact that the two hardest, mission-
defining capabilities are still greenfield and scheduled one-session-each. Everything below is
in service of those three things.

---

## What is genuinely excellent (so the critique is calibrated)

- **The provenance backbone and the fail-loud discipline.** The four-fold tuple, the strict
  frozen pydantic models that make invalid states *unconstructible* (e.g. a `foreign` +
  `validated` certificate literally cannot be built), and the "raise loud, catch once at the
  CLI boundary" pattern are textbook. This is the strongest part of the build and it deserves
  to be.
- **Intellectual honesty in the handoffs.** The Stage 10–12 notes document NO-GOs and CONCERNs
  rather than papering over them, refuse to relax tolerances, and correct their own earlier
  reference values against primary sources. This is the behaviour you *want* and it's the main
  reason I trust the rest.
- **Test design where it counts.** `tests/vv/test_statistical_uncertainty.py` validates the
  estimator against *known analytic answers* (IID recovery of σ/√N, an AR(1) series with
  analytic ESS, the τ_int → 0.5 limit), not just that constructors fire. That's the right
  instinct.
- **Defensive parsing.** The OpenFOAM `load` path reconstructs the force split and cross-checks
  it against the `forceCoeffs` total Cd, raising on disagreement rather than reporting a wrong
  decomposition (`aero/adapters/openfoam/solver.py`).
- **Operational safety.** The cost cap is an append-only ledger with explicit `ORPHANED`-state
  handling that refuses further launches — the right design for real money on rented GPUs.

The codebase is clean: a full-tree scan turned up only **9 debt markers**, and nearly all are
documented stubs inside *frozen-optional* solvers (PyFR/NekRS periodic cases raising
`NotImplementedError`). This is not a project drowning in TODOs.

---

## Critical findings (these bear on whether the thesis succeeds)

### F1 — The delta-uncertainty is unquantified. The flagship guarantee is hollow at its center.

This is the most important finding in the review.

The whole product rests on **IMPROVEMENT-EXCEEDS-UNCERTAINTY**: a reported optimization delta is
thesis-grade only if `delta > k · U95_delta`. But `ImprovementClaim.u95_delta`
(`aero/vv/reportable.py:170`) is a **free input field**. The validator asserts
`delta > k · u95_delta` — and nothing anywhere computes `u95_delta`. A repo-wide grep confirms
it: `u95_delta` appears only as a field and a constructor argument, never as the output of any
estimator. The composition helper that *does* build the three-part RSS (`compose_reportable`)
only handles **single quantities**, not deltas.

So the Constitution's stated composition —
`U95 = RSS(numerical, statistical, input)`, and for a delta "correlated errors cancel… below the
RSS of the two absolutes" — is asserted in prose and **left as a number the caller types in**.
At Stage 15, the headline result ("the CFD-verified delta exceeds its uncertainty") currently
reduces to *"the delta exceeds k times a value the author supplied."* That is the single number
the entire thesis stands on, and today it is unvalidated.

**Why it matters more than the other findings:** it's not a gap in something unbuilt — it's a
hollow core in something already *shipped and gated by CI*. The `small-signal-gate` looks like it
enforces the invariant, but it only enforces an inequality against an unconstrained input.

**Recommended fix (build before Stage 15, not during):**
1. Add a **paired-difference estimator**. Take the two matched time series (candidate — baseline
   at matched phase / mesh-topology / numerics), form the per-cycle *difference* series, and run
   the **existing** NOBM + τ_int machinery on the *difference*. This *measures* the correlated-
   error cancellation instead of assuming it, and yields `u95_delta_statistical` honestly. This
   is the same common-random-numbers / paired-comparison principle the doc already cites — it
   just needs to be code, not a sentence.
2. Compose `u95_delta` from a paired numerical term (GCI on the delta, or matched-grid
   Richardson) RSS the paired statistical term. Add `compose_improvement(...)` alongside
   `compose_reportable(...)`.
3. Record the **empirical correlation coefficient** between the baseline and candidate series in
   the `ImprovementClaim`, so the cancellation is auditable rather than assumed. If the two runs
   turn out weakly correlated (cancellation fails), that should surface — not be hidden inside a
   hand-entered `u95_delta`.

Until this exists, treat any `ImprovementClaim` as provisional regardless of what CI says.

### F2 — The unsteady solver over-predicts thrust 2–4× on its only experiment-anchored case, directly upstream of the flapping flagship.

The Stage 11/12 handoffs are commendably clear about this: the plunging foil converges to
C_T ≈ 0.96, cycle-converged and resolution-insensitive, but that is ~4.5× the digitized
reference; Stage 12 re-checked against the **primary source** (Heathcote's PhD thesis, C_T ≈
0.20–0.22) and concluded the **2-D laminar foil over-predicts by ~2–4×**, with root-cause pushed
to Stage 13.

The reason this is a *critical* finding and not just a logged CONCERN: the plunging foil is the
**"unsteady machinery" validation tier** — the direct precursor to rigid flapping (Stage 14) and
the optimization (Stage 15). The clean win you *do* have (oscillating-cylinder lock-in, St within
0.63%) is a bluff-body **shedding** problem; the foil is **thrust-producing** and much closer to
flapping physics. Everything downstream runs on the solver that is currently 2–4× off on the one
thrust case with experimental data.

**Implications for the roadmap:**
- **Stage 13 is effectively a second hard go/no-go**, not a feature add. If γ-Re_θ transition
  (`kOmegaSSTLM`) — or a laminar/incompressible treatment — does not close the 2–4× gap, then the
  flapping ladder's *quantitative* validity is in question and the Stage-15 optimizer would be
  optimizing a **biased objective**. Recommend elevating Stage 13 to explicit go/no-go status in
  the map with the same STOP discipline as Stage 10, and **pre-registering** the acceptance
  criterion (foil C_T within band of the primary-source HG value) *before* running, so the
  outcome can't be rationalized after the fact.
- **NACA 0012 Cd is a documented NO-GO** (blunt trailing edge is not steady-convergeable). That's
  physically legitimate — a blunt TE sheds, so a steady solver genuinely can't converge it — but
  it means one of the three *table-stakes* canonical cases is unresolved on the steady path. You
  now have the moving-mesh machinery; the honest way to close that gate is to run NACA 0012 on the
  **unsteady** path and report a shedding-averaged Cd with its statistical U95, rather than leaving
  a retained xfail. That converts a NO-GO into a real (if harder-won) GO and exercises the
  unsteady stack on a case with a trusted reference.

### F3 — The two mission-defining stages (15 optimization, 17 meshing) are greenfield, large-scope, and scheduled one-session-each.

- **Stage 15 (the optimizer — the entire point of the project)** currently has only the *output
  schema* (`OptimizationResult`, `ImprovementClaim`). A grep for any optimization machinery —
  Bayesian optimization, BoTorch/Ax, `scipy.optimize`, acquisition functions, design-variable
  parametrization, FFD/morphing, an optimization loop — returns **nothing**. The mission-defining
  capability is 100% unbuilt, and (per F1) the machinery that would make its result *defensible*
  is also unbuilt.
- **Stage 17 (arbitrary-geometry ingestion + robust meshing)** has essentially no foundation.
  `aero/adapters/_meshing/` contains only `gmsh_high_order.py` (167 LoC, for *frozen* PyFR) and
  `nekmesh_wrapper.py` (64 LoC, for *frozen* NekRS). There is no STL/CAD/3MF ingestion, no
  watertightness gating, no repair, no CadQuery/build123d, no `snappyHexMesh` automation; the
  OpenFOAM geometry path is parametric airfoil curves only. Your own mission doc calls automated
  meshing on arbitrary geometry *"the dominant practical failure mode."* It has zero code behind
  it.

**The structural risk:** the "one Claude Code session per stage" cadence worked for Stages 1–12
because those were largely **plumbing over known tools** (wire OpenFOAM, wire SU2, wire a ledger).
Stages 15 and 17 are **open-ended research/robustness problems**, and that cadence is likely to
break on them. Recommendations:
- Split both into explicitly-scoped sub-stages with intermediate go/no-go gates, and budget them
  as multi-session from the outset.
- For Stage 17, adopt your own escape hatch *early*: **optimize in a parametric / FFD / SDF space
  and *emit* manufacturable CAD**, rather than trying to *ingest and robustly mesh* arbitrary CAD.
  Treat robust arbitrary-mesh ingestion as a research track, not a v0.1.0 gating deliverable.
- **Strategic re-sequencing (ties F1+F2+F3 together):** prove a *minimal* CFD-in-the-loop
  optimization — plus the F1 delta-UQ machinery — end-to-end on a **cheap, already-trusted** case
  (a parametric airfoil, or even the validated low-Re cylinder) *before* layering on flapping-
  specific complexity. That buys you (i) an early, cheap, genuinely thesis-grade delta on physics
  you actually trust, and (ii) validation of the F1 machinery *before* you bet it on the 2–4×-off
  flapping solver. Decouple "does the optimization + delta-UQ loop work at all" from "does it work
  on the hard flapping problem."

---

## Provenance & reproducibility gaps (the platform's core selling point)

### P1a — `dvc_input_hash` hashes the sync-diff, not the content identity of the inputs.

`dvc_input_hash` (`aero/provenance/four_fold.py`) hashes `dvc status -c --json`. When everything is
in sync, that output is `{}`, which hashes to a **constant**. Consequence: two runs against two
*different-but-each-in-sync* dataset versions produce the **same** `dvc_input_hash`. The component
records "clean vs the remote," not "these exact bytes."

The true data identity is carried by the committed `.dvc`/`dvc.lock` files (folded into `git_sha`)
— but *only* if every input is pipeline-locked; for any loosely-tracked input the "D" of the
four-tuple is a sync-check, not a fingerprint. The risk is that a reader treats `dvc_input_hash`
as a data fingerprint (the name and the README imply exactly that), and if the remote pointer
moves, provenance silently doesn't notice.

**Fix:** hash the resolved *object hashes* (the md5/checksum fields from `dvc.lock` / `dvc status`
with actual hashes), or hash `dvc.lock` content directly, so "D" is a real content fingerprint.
And document the "git carries dvc.lock, so git_sha is the primary data identity" relationship
explicitly — right now that guarantee is implicit and conditional.

### P1b — A `-dirty` SHA can be tagged thesis-grade. (One-line fix, high value.)

`git_sha(..., allow_dirty=True)` returns `…-dirty`, the pattern permits it, and
`ReportableResult._thesis_grade_gate` checks U95 and anchors but **not** SHA cleanliness. So an
exploration run on a dirty working tree can carry `validation_tag="thesis-grade"` — which
contradicts the definition of thesis-grade. Add to the gate:
`if self.provenance.git_sha.endswith("-dirty"): raise ...`.

### P1c — The SIF digest is recorded, not verified at launch.

`container_sif_sha256` looks up the *expected* digest in `containers/SHA256SUMS` by basename;
nothing re-hashes the SIF that actually ran. Signing covers integrity out-of-band, but the
four-tuple stores the expected, not the observed, digest. **Fix:** hash the SIF at launch and
assert equality with the recorded sum (fail-loud on mismatch). Closes the "SIF swapped, SUMS not
updated" hole and makes the container component a verified fact rather than a lookup.

### P1d — `u95_input = 0` is indistinguishable from "input UQ was skipped."

`u95_input` defaults to `0.0` and the thesis-grade gate never checks whether parametric UQ was
actually performed. A thesis-grade result can silently omit input uncertainty. For a platform
whose pitch is *honest* error bars, "performed and found negligible" must be distinguishable from
"not performed." **Fix:** add `input_uq_performed: bool` (or make `u95_input: float | None` with
`None` = not performed).

---

## Statistical / methodological refinements

### M1 — NOBM at N ≈ 35 cycles is borderline; the error-on-the-error-bar is large.

`n_batches = min(max(4, floor(√N)), 8)`; at N = 35 that's 5 batches of 7. If τ_int ≈ 2–3 cycles,
each batch is only ~2–3 correlation times long, so batch decorrelation isn't guaranteed and the
batch-means SE is itself noisy (the code comments acknowledge this). The `reliable` cross-check
band `[0.5, 2.0]` is a **factor-of-4 in variance** — a weak sanity check, not a tight bound. The
known-answer tests are correspondingly loose (the IID test accepts ±factor-2; the AR(1) test only
asserts `n_eff < 0.7N` when the analytic ESS is `0.25N`).

The consequence chains straight into F1: if `u95_statistical` itself carries ±50% relative
uncertainty at these sample sizes, then `delta > 2·u95` is meaningfully less safe than it looks —
the margin is being computed against a quantity that is itself uncertain.

**Fixes:**
- Tie the batch design to the *measured* autocorrelation: require `batch_size ≥ c·τ_int` (e.g.
  c ≥ 5) and raise/flag when the converged tail can't supply it, instead of a bare √N rule.
- Tighten the known-answer tests to **multi-seed unbiasedness**: average over ~100 seeds and
  assert the estimator recovers the analytic SE to within a few percent. The current tests catch
  gross errors but would miss a systematic 50% bias.
- Consider reporting an interval *on* `u95_statistical` (or switch to overlapping-batch-means /
  a spectral estimator with more stable dof), so the delta-gate margin can account for it.

### M2 — Convergence-detection uncertainty isn't propagated.

The entire statistical term is conditional on a *point estimate* of `converged_from_cycle` from
`detect_cycle_convergence`. If convergence is declared one cycle early, residual transient
contaminates both the mean and the variance, and there's no error budget for that choice.
**Fix (cheap, and it strengthens the headline claim):** sensitivity-test the reported quantity to
the convergence cutoff (± a few cycles) and fold the spread into U95, or at minimum report it as a
diagnostic.

---

## Code & operational

- **`final_residual` is overloaded** to carry RMS-lift amplitude in the unsteady path
  (`aero/adapters/openfoam/solver.py`, `final_residual=float(cl_w.std())`). A field named for a
  convergence residual holding a physical amplitude is a latent foot-gun for anyone who later
  reads `final_residual` expecting a residual. Give it a dedicated field.
- **Recurring infrastructure ceiling: MPI/PMIx is blocked in the LXCs.** Multiple handoffs (SU2,
  plunging foil) report `mpirun`/PMIx failing at the namespace level — no multi-rank parallelism,
  single-node only. This caps achievable mesh resolution and makes cases slow, and it will bite
  *hardest* on 3-D rigid flapping (Stage 14), FSI (18–19), and any surrogate-training data
  campaign. Recommend making "working MPI in the compute environment (or heavy cases on a proper
  HPC/cloud allocation)" an **explicit prerequisite before Stage 14**, rather than a per-case
  surprise.
- **Security guardrails fail *open*.** `block-dangerous-bash.sh` and jq-dependent hooks fail open
  without their dependencies (Stage 02/03). For a platform that runs container workloads as LXC
  root, a fail-open guardrail is worth closing.
- **Minor drift / citability polish:** `pyproject.toml` still declares `version = "0.0.1"` and
  `Development Status :: 1 - Planning` while the tag is `v0.0.12`; the README's `pip install aero`
  is aspirational (not on PyPI, and "aero" is almost certainly taken). Both are cheap to align and
  both matter for the "thesis-grade, citable" story.

---

## Prioritized action list

**Do before Stage 15 (they gate the flagship result's credibility):**
1. **F1** — build the paired-difference `u95_delta` estimator + `compose_improvement()`; record
   the baseline–candidate correlation. *Nothing downstream is defensible without this.*
2. **P1b** — reject `-dirty` SHAs in the thesis-grade gate (one line).
3. **P1d** — make "input UQ skipped" distinguishable from "input UQ ≈ 0".
4. **M1** — tie batch size to measured τ_int; tighten the estimator's known-answer tests to
   multi-seed unbiasedness.

**Do as part of Stage 13 (treat it as a real go/no-go):**
5. **F2** — pre-register the foil acceptance criterion; root-cause the 2–4× over-prediction; close
   NACA 0012 on the unsteady path instead of leaving the NO-GO xfail.

**Do before Stages 14 / 17 (de-risk the scaling and the greenfield):**
6. **F3** — re-sequence to prove the optimization + delta-UQ loop on a cheap trusted case first;
   split Stages 15 and 17 into gated sub-stages; adopt the parametric-FFD-emit-CAD path for 17.
7. **MPI** — get multi-rank working (or budget a real HPC/cloud allocation) before 3-D flapping.

**Provenance hardening (the selling point — do opportunistically but don't skip):**
8. **P1a** — make `dvc_input_hash` a true content fingerprint; document the git–dvc.lock identity.
9. **P1c** — verify the SIF digest at launch, don't just look it up.

**Polish (cheap, improves the citability narrative):**
10. Align the package version with the tag; fix or qualify the `pip install` instruction;
    rename the overloaded `final_residual` field; close the fail-open hooks.

---

## Closing note

The thing to protect here is that the project's *stated* virtue — trustworthy, reproducible,
honestly-bounded results — is almost entirely real in the code, with two exceptions that happen to
sit at the most load-bearing points: the delta-uncertainty at the center of the flagship claim
(F1), and the 2–4× solver discrepancy one tier upstream of it (F2). Fix those two, prove the
optimization loop on cheap trusted physics before betting it on flapping, and the rest of this is
already built to a standard most funded labs don't reach. The honesty already in the handoffs is
your biggest asset — the recommendations above are mostly about making the *code* enforce the
standard the *documentation* already holds itself to.
