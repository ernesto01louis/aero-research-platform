# STAGE 10 — V&V Debt Retirement + Output-Validity Bar

> **HARD GO/NO-GO stage.** This is the gate for the entire optimizer mission. No
> optimization delta and no flapping result is thesis-grade on a solver that misses the
> canonical cases. If the canonical set cannot reach tolerance, **STOP and rethink** the
> mesh/scheme/solver strategy before investing further — do not relax a tolerance and do
> not proceed to build on an untrusted solver.

## BEFORE YOU START — READ

1. `CLAUDE.md` (auto-loaded) — esp. the optimizer-mission block + Hard Rules 12–17.
2. `.aero-stage` (flip to `10` as this stage's first commit).
3. `docs/handoffs/STAGE-09-domino-baseline-surrogate-DONE-2026-06-01.md` §13 (close-out).
4. `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` (governing scope) + `README-handoff.md`
   (the map + guardrails).
5. ADR-005 (TMR V&V harness), ADR-013 (mission refocus), ADR-014 (budget; bump the cap),
   ADR-015 (constitution invariants 10–11, in 72 h review).
6. `.claude/rules/{flapping-validation-ladder,optimization-integrity,fail-loud-pydantic}.md`.
7. Run first to verify the world: `pytest tests/stage_09 tests/unit -q`, `mypy aero`,
   `ruff check aero scripts tests` (all green at the Stage-09 close-out SHA).

## Why this stage

The forward solver carries three failing canonical V&V cases (Stage 05, tolerances never
relaxed): NACA 0012 Cd **+21%** (trailing-edge pressure drag; a blunt-TE C-grid is built
but unvalidated), turbulent flat-plate Cf **7–15%** off, 2D bump converges too loosely for
a reliable GCI. The mission (CFD as ground truth for reported improvements) cannot stand on
that. **And** the existing cases are fully-turbulent RANS, while the flapping mission is
low-Re laminar/transitional/unsteady — so the canonical set must also cover the mission's
own flow regime. This stage retires the debt, adds regime-relevant cases, and ships the
operational definition of "thesis-grade output."

## Deliverables

1. **Retire the turbulent canonical debt.** Drive NACA 0012 Cd, flat-plate Cf, and the 2D
   bump to within tolerance (Cd 3%, Cf 5%, Cp 3%). Use the built blunt-TE C-grid; run the
   mesh-sweep on `aero-vv` (CPU cluster; submit via `scripts/run_long.sh`, poll — never
   hold the SSH session). Mesh independence, y⁺ < 1, scheme/BC review. Un-xfail
   `tests/vv/test_tmr_naca0012.py` (and the flat-plate/bump tests) **only** when the case
   genuinely passes.
2. **Add forward-regime canonical cases** the optimizer's flapping work actually uses:
   - Laminar flat plate vs **Blasius** (skin-friction + boundary-layer profile).
   - Low-Re cylinder **vortex-shedding Strouhal** vs the canonical St–Re relation.
   - A **laminar/transitional airfoil** case (sanity for the low-Re regime; transition
     model wiring is Stage 13, so a laminar baseline here).
   Reference data DVC-tracked under `data/reference/<case>/` with a `reference.md`.
3. **Output-validity bar.** `docs/vv/output-validity-bar.md` — the operational definition of
   "thesis-grade output": required validation tolerances vs reference, four-tuple
   completeness, the U95 composition `RSS(numerical, statistical, input)`, and the
   improvement criterion `|delta| > k·U95` (k default 2). Plus `aero/vv/reportable.py`
   **schema skeleton** (`ValidationAnchor`, `ReportableQuantity` with the three U95 fields +
   `u95_total`, `ReportableResult` with an optional `ImprovementClaim`) — strict pydantic,
   stdlib+numpy+pydantic only (PLATFORM-NOT-HUB). Full U95 composition + the CI gate land
   Stage 12; this stage defines the contract and the types.
4. **Budget cap bump (ADR-014).** `aero/orchestration/cost_cap.py` default $50 → $150;
   update `tests/stage_07/test_cost_cap.py`.
5. **Merge the ADR-015 constitution PR** once the 72 h review has elapsed and the operator
   has approved (Invariants 10 + 11). CLAUDE.md already carries the rules at hard-rule level.
6. ADR if any new decision is made (e.g. a mesh-strategy change to pass NACA). Post-stage
   handoff + author the Stage-11 prompt. Tag `v0.0.10`.

## The GO/NO-GO gate

**GO** = the canonical set (turbulent table-stakes **and** the forward-regime cases) reaches
stated tolerance, with mesh independence demonstrated (GCI in the asymptotic range). The
xfails flip to passing; the validity-bar doc + schema are merged.

**NO-GO** = if any canonical case cannot be brought to tolerance, **STOP**. Write up the
root cause (mesh, schemes, BCs, solver choice) and the candidate strategies, and bring it to
the operator before building anything that depends on the solver being trusted. Do **not**
relax a tolerance; do **not** proceed to Stage 11 on an untrusted solver.

*Engineering note:* the turbulent-RANS cases are table-stakes credibility; the forward-regime
cases are the ones the flapping optimizer directly depends on. If a turbulent case proves an
off-regime deep mesh-craft rabbit hole, that is itself a "rethink" trigger to bring to the
operator — not a quiet bypass.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-10-vv-debt-and-validity-bar-DONE-YYYY-MM-DD.md` with the full
frontmatter + 10 sections (`.claude/rules/handoff-discipline.md`). Emphasize: the go/no-go
outcome (which cases pass, with the GCI evidence + MLflow runs); the validity-bar contract;
the constitution-PR merge state. Confirm the **Stage-11 prompt exists** at
`docs/handoff-bundle/STAGE-11-moving-mesh-and-unsteady.md`. Then tag `v0.0.10`.
