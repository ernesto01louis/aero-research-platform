---
# Required frontmatter — scripts/check_handoff_exists.sh parses these.
stage: 10
stage_name: "Stage 10 — V&V Debt Retirement + Output-Validity Bar"
status: partial
date_started: 2026-06-15
date_completed: 2026-06-15
session_duration_hours: 0
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-4-8
git_sha_start: "632678fda0d76dcf2a920f13bfd60ddd6ec8e237"
git_sha_end: "632678fda0d76dcf2a920f13bfd60ddd6ec8e237"
stage_tag: v0.0.10
next_stage: 11
next_stage_name: "Stage 11 — Moving Mesh & Unsteady"
---

# Stage 10 — V&V Debt Retirement + Output-Validity Bar — IN PROGRESS (2026-06-15)

> **STATUS: partial / in-progress.** This handoff is being written incrementally so the
> Stop-hook gate passes and so a session that resumes across an IDE relaunch (to load the
> provenance env) picks up exactly where we are. `git_sha_end` is provisional (= start SHA)
> until the session completes; it is corrected at the `v0.0.10` tag. The authoritative
> live state is this file + the `stage-10/vv-debt-naca0012` branch.

## 0. Where we are right now (read this first on resume)

The Stage-10 V&V-debt session opened with a **pre-cluster adversarial validation** of the
never-cluster-tested Stage-09 blunt-TE C-grid (the NACA 0012 fix). That validation returned
**NO-GO with 4 confirmed blockers** — meaning a cluster run *as-is* would have (a) failed
`checkMesh`, (b) had an invalid base BC, (c) been unmeasurable, and (d) been unable to pass
3% anyway. We are fixing those on this branch **before** spending cluster CPU.

**Operator decisions (this session):**
- **NACA 0012 → "diagnostic + honest NO-GO".** Fix the mesh, add a minimal pressure/viscous
  drag decomposition, pin the reference, run ONE diagnostic cluster solve to *measure* the
  real Cdp/Cdv + the improvement, then document root cause and keep it xfail with an
  evidence-based reason. Do **not** chase a 3% pass this session.
- **Provenance env → operator exports the 4 vars (`AERO_PROVENANCE_DSN` + MLflow/MinIO) in
  the shell that launches `claude`, then relaunches.** The reload that prompted this resume
  did NOT propagate `settings.local.json`'s `env` block into Bash subprocesses, and
  `aero vv run` hard-fails without `AERO_PROVENANCE_DSN` (`aero/provenance/db.py:resolve_dsn`).
  Mesh `blockMesh`/`checkMesh` validation needs none of this — only the solve does.

**Sequencing:** land + commit all code fixes + verify the mesh via `checkMesh` (no env), THEN
operator exports vars + relaunches, THEN run the provenance-backed diagnostic solve + sweep.

## 1. Deliverables status

| # | Deliverable (verbatim from stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Retire turbulent canonical debt (NACA 0012 Cd, flat-plate Cf, 2D bump) | ⚠️ | In progress. NACA → diagnostic+NO-GO (see §2/§3). Flat-plate xfail is self-milestoned **stage-12** (correlation-spread), bump → **stage-10** convergence tuning (not yet started). |
| 2 | Add forward-regime canonical cases (Blasius plate, cylinder Strouhal, laminar airfoil) | ❌ | Not started. |
| 3 | Output-validity bar (`docs/vv/output-validity-bar.md` + `aero/vv/reportable.py` + tests) | ✅ | Landed at Stage-09 close-out (`reportable.py`, `tests/stage_10/`, 22 tests). Verify green this session. |
| 4 | Budget cap bump $50 → $150 (ADR-014) | ✅ | Done (commit 632678f); `aero/orchestration/cost_cap.py`. |
| 5 | Merge ADR-015 constitution PR (Invariants 10 + 11) | ✅ | Ratified/merged 2026-06-15 (PR #15). |
| 6 | ADRs + post-stage handoff + Stage-11 prompt + tag v0.0.10 | ⚠️ | ADR for the blunt-TE mesh fixes pending; handoff = this file; Stage-11 prompt + tag pending. |

## 2. Decisions made

- **Run an adversarial pre-cluster validation of the blunt-TE C-grid before any solve.**
  Rationale: the grid was built in Stage 09 and *never cluster-validated*; CPU cluster time
  is scarce. The 4-dimension workflow (routing / geometry / mesh-topology / drag-physics,
  each finding adversarially re-checked) found 4 confirmed blockers — none of which a cluster
  run would have surfaced cheaply. Validating first **saved** the wasted cycles.

- **NACA 0012 is a "diagnostic + honest NO-GO", not a pass-attempt** (operator-chosen).
  Rationale (the arithmetic): friction is held fixed at the Stage-05 measured 0.006711, the
  3% pass ceiling is ~0.00836, leaving only ~0.00165 for pressure+base drag; best case
  (genuine pressure ~0.0015 + smallest base drag ~0.00025) lands ~+4.2%, and likely higher if
  the suspected friction over-prediction is real. Blunt-TE alone *cannot* close 3%. Rejected:
  "drive to PASS" (would need base-BL re-engineering + a friction investigation, may not
  converge this session, risks stealth tolerance pressure) and "defer entirely to Stage 12"
  (loses the chance to measure the real decomposition now). Honest NO-GO with measured
  evidence is the rigorous middle path and matches the prompt's "document the root cause."

- **Split the blunt base into its own `airfoil_te` wall patch with `nutUSpaldingWallFunction`.**
  Rationale: the base's wall-normal direction *is* the shared wake-cut streamwise direction,
  so it cannot get y⁺<1 resolution without breaking conformality with UW/LW; Spalding is valid
  across all y⁺. Keeps the validated surface treatment (`nutLowReWallFunction`, y⁺<1)
  untouched and lets the diagnostic measure base drag on its own patch. Rejected: leaving the
  base on the `airfoil` patch with `nutLowReWallFunction` (a confirmed-invalid BC at y⁺~2300).

- **Add a minimal pressure/viscous drag decomposition now** (a `forces` FO + loader parse +
  two optional `SolveResult` fields), pre-empting a thin slice of the Stage-11 post-process
  toolkit. Rationale: the central NACA hypothesis ("excess is *entirely* pressure drag") is
  currently un-testable by the harness — the 0.0031/0.0067 split was hand-read off a Stage-05
  log. Without the decomposition the diagnostic cannot answer the go/no-go honestly.

- **Reference data:** the TMR mirror (`tmbwg.github.io`) gives grid-converged **SST** Cd at
  α=0 as **0.00809 (CFL3D) / 0.00808 (FUN3D)**; our `reference.md` value 0.008120 is actually
  the **SA** number, mislabeled "SST" (<0.5%, inside tolerance, but a provenance error to
  fix). The page publishes **no Cdp/Cdv split**, so the friction question is resolved only by
  the diagnostic run + literature, not the reference summary.

## 3. Validation findings (the blunt-TE C-grid GO/NO-GO)

Confirmed blockers (all upheld at high confidence after adversarial re-check):
1. **bw-grading-mismatch** — the base-wake (BW) block graded `simpleGrading (1 1 1)` while
   neighbours UW/LW grade the shared streamwise edges with `e_wake`≈917 → duplicate unmerged
   points on the shared internal faces → **`checkMesh` fails / mesh invalid**.
   Fix: `simpleGrading (e_wake 1 1)` on BW (`case_writer.py:160`).
2. **bw-base-no-bl** — the blunt base wall has no wall-normal resolution (first cell ≈ 0.01c
   after the grading fix → y⁺~2300) so `nutLowReWallFunction` (y⁺<1) is invalid there; the
   base also never enters the asymptotic GCI range. Fix: split base → `airfoil_te` patch +
   `nutUSpaldingWallFunction`.
3. **no-drag-decomp-in-loader** — the loader surfaces only *total* Cd; `forceCoeffs1` has no
   pressure/viscous split; `SolveResult` has no such fields. The hypothesis is un-testable as
   built. Fix: `forces` FO + loader parse + `SolveResult.cd_pressure`/`cd_viscous`.
4. **blunt-te-cannot-close-3pct-arithmetic** — closed-form: blunt-TE alone lands ~+4.2% best
   case; it improves but cannot pass 3% (friction held fixed; base drag additive). Drives the
   diagnostic+NO-GO decision.

Upheld major (real, lower-risk): **te-thickness-value-is-gate-only** — `trailing_edge_thickness`
is a boolean `>0` gate; the actual TE thickness (0.00252c full) is fixed by the NACA open-TE
coefficient `_A4_OPEN_TE=0.1015`, so the float value never sizes the mesh (a FAIL-LOUD /
provenance-fidelity gap). Fix: add a `model_validator` reconciling the field with the
geometry's open-TE thickness (else fail loud). **friction-claim-internally-inconsistent** —
"friction ~2% correct" only holds under a friction-heavy reference split; the conventional
TMR split (Cdv~0.0060–0.0061) would make our friction ~+10% high — a co-equal error blunt-TE
can't touch. Resolve via the diagnostic decomposition.

Refuted false alarms (adversarial verification did its job): "reference is sharp-TE/SA" and
two turbulence-model-mismatch claims — reference and solve are both k-ω SST; the +21% was a
sharp-vs-sharp comparison; blunt-TE is the standard open NACA 0012 TE (a numerical remedy).

## 4. Environment / dependency / schema changes

- `SolveResult` (`aero/adapters/_base.py`): two new optional fields `cd_pressure`,
  `cd_viscous` (default None; back-compat for non-airfoil cases). [pending commit]
- `CaseSpec` (`aero/adapters/openfoam/schemas.py`): `trailing_edge_thickness` reconciled with
  the geometry's open-TE thickness via a validator. [pending commit]
- No new pyproject extras; no DB/bucket changes; no container SHA changes.

## 5. CI/CD changes

None yet. (Tests updated under `tests/stage_09` + a new decomposition-parse unit test.)

## 6. Gotchas discovered

- `settings.local.json`'s `env` block does NOT reach Bash subprocesses in this Claude build;
  `aero vv run` hard-fails without `AERO_PROVENANCE_DSN`. Operator exports the vars in the
  launching shell instead.
- The NACA 0012 V&V case routes through `case_writer.py` (the blunt-TE path), **not** the
  TMR-specific `tmr_case_writer.py` — confirmed; the blunt-TE code is live for this case.
- The Stop hook blocks every turn-end unless a Stage-10 handoff with valid frontmatter exists
  — hence this partial handoff was committed as the first Stage-10 commit.

## 7. Open items for the next stage (and beyond)

- **This session, post-relaunch:** run the diagnostic NACA solve + 3-grid sweep through
  `aero vv run` (provenance on); record measured Cdp/Cdv + total Cd; finalize the honest
  NO-GO write-up + updated xfail reason; then the bump-convergence work + forward-regime cases.
- **Stage 11 prompt** must exist at `docs/handoff-bundle/STAGE-11-moving-mesh-and-unsteady.md`
  before the v0.0.10 tag (not yet written).
- Flat-plate Cf is self-milestoned to **Stage 12** (correlation-spread); not in this stage's
  pass scope.

## 8. Pointers for next session

- **Read first:** this file (§0), then `git log --oneline origin/main..stage-10/vv-debt-naca0012`.
- **Do not re-read:** the full validation transcript — its conclusions are in §3.
- **Run first to verify:** `pytest tests/stage_09 tests/unit -q`, `ruff check aero`, `mypy aero`.
- Validation workflow run id (this session): `wf_87cabf34-6aa` (cached if resumed).

## 9. Artifacts produced

[To be completed at session end — see the branch diff.] So far: branch
`stage-10/vv-debt-naca0012`; `.aero-stage`→10; this partial handoff.

## 10. Confidence / risk note

High confidence: the 4 blockers are real (adversarially verified, with empirical/numerical
checks); the grading + base-patch fixes are mechanically sound and `checkMesh`-verifiable
without the env. Medium: the exact `force.dat` column format of the ESI v2412 SIF — the
loader parser is written defensively + unit-tested on a synthetic sample, and validated
end-to-end by the diagnostic run. Open: whether the diagnostic confirms a friction
over-prediction (the co-equal suspect); that is what the run measures.
