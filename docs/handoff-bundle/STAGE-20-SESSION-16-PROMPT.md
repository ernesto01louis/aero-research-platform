Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). Resuming a partial stage, session 16.
Repo /root/projects/aero-research-platform, branch stage-20-flexible-flapping-wing-fsi (verify
the tip with `git log`), PR #44 (draft). `.aero-stage` is still **20** — do not bump it. Status
stays **`partial`**. **No tag.**

**⛔ STAGE 20 ENDED IN A RECORDED NO-GO ON INFRASTRUCTURE (ADR-041 V7 FIRED, 2026-09-20).** The
gated flexible-arm campaign cannot be run on this stack, both levers are exhausted, and the
verdict is written. **There is nothing to submit, nothing to restart, and no campaign to resume.**
This session is bookkeeping and the Stage-21 question — not compute. If you find yourself
preparing a run, stop and re-read §6.89.

FIRST COMMAND BLOCK — read-only; it exists to prove the box is IDLE and must stay that way:

    ssh root@aero-dev 'pgrep -c "pimpleFoam|ccx_preCICE|mpirun" || echo 0; uptime'
    systemctl is-active aero-progress.service
    cd /root/projects/aero-research-platform && git status --short && git log --oneline -3
    python3 -m json.tool data/vv/stage20_nogo_infrastructure.json | head -20

Expected: **0** processes on aero-dev; `aero-progress.service` **active** (a read-only sampler +
ntfy notifier on the Proxmox host — NOT a campaign process; it may still hold state for the two
dead runs); a clean tree; the verdict record present. If anything is running on aero-dev, someone
started it outside this record — find out what before touching anything.

READ FIRST, IN THIS ORDER:

1. CLAUDE.md and `.aero-stage`.
2. **`docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` §6.88 and §6.89** —
   the two restart attempts (measured) and THE VERDICT. Everything else is context.
3. `data/vv/stage20_nogo_infrastructure.json` — the machine-readable verdict.
4. `docs/handoff-bundle/STAGE-20-RESUME.md` — the banner at the top. Everything below it predates
   the verdict.
5. **ADR-041's "V7 — FIRED"** and **ADR-045's "R6 — EXECUTED" + amendment A19**.
6. CHANGELOG.md `[0.0.20]`.

STATE — settled; do not re-derive, do not re-litigate:

- **The NO-GO is on INFRASTRUCTURE** for the ADR-039/040 gated campaign at Stage 20's frozen pins.
  It is **not** a finding about the Heathcote-Gursul physics, **not** that any solver is
  incorrect, **not** about chordwise flexibility. Q1 equivalence passed on both stacks and the
  rigid arm completed 76 090/76 090 windows. Do not let anyone widen it.
- **≈37 900 windows per death** against **1 166 675 per wave** ⇒ ~31 expected deaths (~17 at B4's
  floor). The adopted α = -0.05 removed the divergence and raised mean-time-to-crash ~22x; the
  crash remained. That separation is the finding.
- **Lever (a), remove the bug: exhausted.** ASan hunt = `no-report-died`, NOT exoneration; no
  patchable line; the uninstrumented libraries can absorb the store.
- **Lever (b), survive the bug: exhausted**, under a controlled A/B one config mutation apart.
  Both coupled restarts died with **zero** coupling windows past the restart. A18 was necessary
  and not sufficient. The **solid-side** checkpoint/restart is verified byte-identical and IS the
  durable deliverable; the **coupled** restart is not achievable here.
- **R3 has NO verdict.** It was never evaluable (ADR-045 A19) — the scorer never ran. Never write
  that R3 returned `fail`.
- **The residual is measured, not root-caused:** the restarted fluid's first solved Force
  normalizes ~149x segment 1's at the same window and iteration slot; `cellDisplacementx` initial
  residual 1.2269e-02 / 1.2258e-02 / 9.8005e-01 against 3.4982e-04. It is **not** a ddt-order loss
  (the case runs Euler; ADR-045 F2 is not refuted, its scope is the flow-field ddt order). The
  empty quasi-Newton history's contribution is **UNMEASURED** — the run died at coupling iteration
  3, so no `QNColumns` datum exists.
- **B0:** ≈5.86 h bought two failed restarts and zero scoreable windows. Remaining is ≈88 h
  (box-time reading) or ≈66 h (sum-of-submissions) — the two readings were never reconciled and
  the NO-GO forecloses the question.

YOUR TASK — in this order; none of it touches a solver:

1. **The Stage-21 / v0.1.0 question — the one real decision, and it is the operator's.**
   `README-handoff.md` defines Stage 21 as optimization over flexible-flapping FSI plus the
   RESULTS-MUST-TRAVEL bundle, with v0.1.0 after it. That capability has no validated verdict, so
   Stage 21 as written would optimize over an unvalidated capability — exactly what Hard Rules 14
   and 15 forbid. Put the options to the operator (proceed on the rigid arm and the verified
   coupling machinery only / defer flexible-flapping optimization past v0.1.0 / re-scope Stage 21),
   with the cost and the risk of each. Do not choose for them.
2. **Finish the handoff's own hygiene** if any remains: §1's deliverables table, §8's pointers,
   §9 and §10 were refreshed at the NO-GO; re-read them and fix anything still stale.
3. **Decide the session-14/15 plan files** (`/root/.claude/plans/*.md`): they are the only
   narrative of how the two levers were exhausted and they live OUTSIDE the repo. Either copy the
   relevant ones into `docs/` or record explicitly that they are not preserved.
4. Keep the record current. Nothing else.

STOP GATES — present and wait:

| Gate | Trigger |
|---|---|
| Stage 21 scope / v0.1.0 | operator-only (task 1) |
| Reopening ANY lever | needs a NEW ADR **and** the operator's word — see ADR-045 "R6 — EXECUTED" for what is and is not ruled out |
| Any B0 spend | there is none to spend on this campaign; a new run needs a new ADR |
| Destructive / non-aero LXC / provisioning | propose-first, literal `approved` |

HARD DON'TS — these have all bitten, or would undo the verdict:

- **Never create `data/vv/stage20_adr045_r3.json` or `data/vv/stage20_n3_confirmation.json`.**
  Their ABSENCE is load-bearing — the R7 gate refuses a gated restarted solve by it. Pinned by
  `tests/unit/test_adr045_r3_record_stays_absent.py`.
- Do not fill `<<B1-PENDING-N3>>`, `<<B2-PENDING-ADR040>>`, `<<B3-PENDING-CEILING>>` or
  `<<B2-PENDING-I4>>`. They are permanently unfilled and the tests hold them.
- Do not retry either failed restart, another `initialize`/config variant of A18, a different
  restart window (w400 was refuted by its own calibration), a wider ASan hunt, or N3 attempt 3.
- **Never cancel a self-hosted CI job**; **never `run_long.sh wait`**.
- Never relax a pre-registered band; never widen Q1's 2 %/5 %/5 %.
- `.venv` on PATH for every commit; `git log` after every commit; `<type>(stage-20): …` headers
  **≤ 100 chars**; quotes in commit messages via heredoc.
- **Do NOT force-push to fix commit-lint on `0b6d774`** without reading §6.89's note: `0b6d774` is
  the PARENT of `f4279f2`, and `f4279f2` is the `provenance.git_sha` baked into BOTH of attempt
  2's on-NFS records — the decisive NO-GO evidence. Rewriting it orphans that SHA.
- **UNTOUCHABLE — these are now the evidence base for a recorded NO-GO. Deleting or overwriting
  one destroys the only record of why the campaign stopped. Read-only, permanently; a future
  session that needs disk space frees it somewhere else:**
  stage20-screen{,9}; the I4 pair `-20260810-1447*`; the Q1 pair `*-20260812-2159*`; both N3
  attempt-1 runs; both N3 attempt-2 runs (`-20260914-1225*`); the mining dir;
  `hg2007_flexible_foil-20260912-161321` (R3's control) **and**
  `hg2007_flexible_foil-20260910-084806` (D-C1, the A17 reference draw — the PAIR is the two-draw
  noise floor; either one missing and the calibration can never be re-derived); the ASan hunt
  `-20260915-113918` and its sibling `-113507`; and **the two failed R3 attempts
  `hg2007_flexible_foil-20260916-152606` (pre-A18 arm) and `hg2007_flexible_foil-20260916-213116`
  (A18 arm)** — each carries `r3-treatment-submission.json`, `restart-seg2-submission.json`, the
  `*.seg1.*` rotations, and the w4000 checkpoint whose sha256 still matches the restart record
  (`0980a299e02b91c2…` / `31fdb9b5b1a95c83…`). Both dirs carry a `README-NO-GO.md` explaining what
  they are.

Final state each session: clean tree, pushed, `pytest -q tests/unit tests/stage_20` green, nothing
running on aero-dev, status `partial`, no tag.
