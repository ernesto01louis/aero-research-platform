Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). Resuming a partial stage,
session 14. Repo /root/projects/aero-research-platform, branch
stage-20-flexible-flapping-wing-fsi (tip = latest on the branch — verify with git log),
PR #44 (draft), **1017 tests green + 3 pre-existing skips**
(`PATH="$PWD/.venv/bin:$PATH" pytest -q tests/unit tests/stage_20`), mypy clean on aero/,
tree clean, pushed.

**Two things are open, and they are sequenced, not parallel.** One diagnostic run may still
be on aero-dev; one ADR is drafted and waiting on the operator. Read both before acting.

FIRST COMMAND, BEFORE ANYTHING ELSE — is the box busy?

    bash scripts/run_long.sh status root@aero-dev fsi-hg2007_flexible_foil-20260915-113918
    ls /mnt/aero-nfs/runs/hg2007_flexible_foil-20260915-113918/tutorial/asan-solid.* 2>/dev/null
    ssh root@aero-dev 'pgrep -x pimpleFoam; pgrep -x ccx_preCICE; pgrep -x mpirun; true'

That run is an **AddressSanitizer hunt** for the heap corruption that has killed five runs.
If it is still `running`, poll it and **run nothing else on aero-dev**. If it is terminal,
its result decides the whole session — read ADR-045 R6 before interpreting it.

READ FIRST, IN THIS ORDER — all of them, before writing anything:

1. CLAUDE.md and .aero-stage (still 20, do not bump).
2. docs/handoff-bundle/STAGE-20-RESUME.md — **§6w (the sanitizer hunt), §6x (ADR-045),
   §6v (the NO-GO), §6u, §6t**, then §7's START-HERE header. §6w and §6x are the two that
   matter today; the sections below them are newest-first history.
3. docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md — **§6.71 (the
   death arithmetic that produced the NO-GO), §6.72 (the sanitizer hunt), §6.73 (what
   reading the source changed about checkpoint/restart)**, then §7.
4. **docs/adrs/ADR-045-checkpoint-restart-for-the-coupled-flexible-arm.md — PROPOSED, not
   accepted.** Read it whole. R6 is the clause that reads the sanitizer result; R5 is the
   hazard that will otherwise be discovered expensively; R3 is the pre-registered
   transparency test.
5. ADR-041 (the ladder, **V7 = the NO-GO clause**), ADR-043 (α = -0.05 of record),
   ADR-044 (the Z-family adoption rule). ADR-039/040 are FROZEN and digest-pinned;
   their FORBIDDEN lists carry over unconditionally.

STATE — settled; do not re-derive, do not re-litigate:

- **The mitigation works and the crash is independent of it.** α = -0.05 (CalculiX's own
  default, which ADR-039 C2 had overridden to zero) eliminated the period-2 divergence.
  N3 attempt 2 then died at w21 897 of 76 090 anyway, with the solid quiet for its last
  7 698 windows. Adopted stack: **37 897 windows per death** vs unmitigated's ~1 729.
- **The arithmetic that is the actual blocker:** a wave is **1 166 675 windows** ⇒ **~31
  deaths per wave, ~17 even at B4's 10-cycle floor.** Scope reduction cannot rescue it.
  **ADR-041 V7 pre-registered this as the NO-GO-on-infrastructure conversation, and it is
  formally OPEN with the operator.** Nothing has been resubmitted.
- **B0 has ~79 h left** as of session 13's open; the sanitizer hunt costs ~4-5 h of it.
  A third N3 attempt needs ~74 h. Surface the arithmetic before proposing any spend.
- Q1 PASSED on the adopted stack (all three frozen bands). The digest pins name N3
  attempt 2's live submissions. The `<<B2-PENDING-I4>>` marker stands unfilled permanently.

WHAT IS RUNNING — the sanitizer hunt, and how to read it

`fsi-hg2007_flexible_foil-20260915-113918` — flexible only, uncontended, 8000 windows,
`--hht-alpha 0.0 --solid-sif calculix-precice-address.sif --asan`. Record:
`/mnt/aero-nfs/runs/hg2007_flexible_foil-20260915-113918/asan-hunt-submission.json`.
Reports land as `<run>/tutorial/asan-solid.<pid>`.

It runs on the **unmitigated** stack deliberately: α = 0.0 dies every ~1 729 windows, so
under ASan's ~2.5x the reproduction costs ~4 h instead of ~88 h. **It is a DIAGNOSTIC run
and sizes nothing** — it is off the campaign stack in two ways at once, and
`is_campaign_configuration`'s third conjunct (solid-sif-of-record) already refuses it.

**Do NOT re-chase the first finding.** ASan's first stop was a global-buffer-overflow READ
12 bytes off a 5-byte `'NODE'` literal via gfortran's string compare at `keystart.f:71`
during deck parsing. It fires on every run including two that completed 8000 windows, and
a READ cannot corrupt heap metadata. `intercept_memcmp=0:halt_on_error=0` removed it from
the path without touching heap checking.

Three readings, per ADR-045 R6:

- **Names a line we compile** (the adapter's own C — upstream fixed a *different* invalid
  free in that file three weeks ago): propose the patch, rebuild the campaign SIF, and the
  checkpoint work becomes optional. This is the good outcome.
- **Names CalculiX Fortran we do not maintain:** upstream report, and ADR-045 becomes the
  path — but only if its R3 passes.
- **No report at all: this is NOT exoneration.** ASan's allocator can shift the layout
  enough to hide the bug. Say so; do not record it as clean.

WHAT IS WAITING — ADR-045, proposed

The commit that added it is the DRAFT. **Acceptance is the operator's explicit word and a
separate commit flipping the Status line**, exactly as ADR-041 through ADR-044 were done.
Do not implement, do not rebuild a container, do not spend B0 before that.

Five facts were measured off disk and source, not assumed — three of them inverted the
obvious design, and all five are in handoff §6.73 with file:line citations:

- The **fluid already checkpoints** every 2000 windows, two generations, **including the
  deformed `polyMesh`**; its `ddtSchemes default Euler` is what makes that restart exact.
- The **adapter says `restart` zero times** but already assembles the complete window-start
  state in named arrays at `nonlingeo_precice.c:1685`.
- **CalculiX's own restart is the wrong tool twice**: `restartwrite` fires at STEP end and
  this case is one step of `INC=400000`, and `accold` appears zero times in
  `restartwrite.f`/`restartread.f`.
- `plunge.amp` has **no `TIME=`**, so a naive restart replays the prescribed plunge from
  zero against a late displacement field — **and produces numbers instead of an error**.

YOUR TASK, IN THIS ORDER

1. Run the FIRST COMMAND block. If the hunt is still running: poll it, do local work only,
   and put nothing else on aero-dev. Never `run_long.sh wait`.
2. When it lands, read the report (or its absence) against R6's three readings and record
   the verdict in the handoff and RESUME **before** proposing anything.
3. Put the R6 outcome to the operator together with the ADR-045 acceptance question — they
   are one decision, not two. If ASan gives a patchable line, the honest recommendation is
   to patch first and defer the checkpoint work.
4. Only on acceptance, implement ADR-045 in the order its clauses state, each commit
   suite-green. The deck change (`TIME=TOTAL TIME`) moves `config_hash` and lands with a
   same-commit re-pin; verify it moves the record and not the numbers.
5. R3 before anything restarted is trusted. Its control is **already bought** — the
   completed 8000/8000 Z4 re-probe `hg2007_flexible_foil-20260912-161321` — so the test is
   one ~3 h uncontended probe, not two. All four clauses were checked against that run's
   actual files; do not redesign them.
6. **The NO-GO conversation is still open.** If ASan finds nothing patchable and R3 fails,
   that is the recorded outcome and it is a result, not a failure. Do not go looking for a
   sixth lever.

STOP GATES — present and wait; do not proceed on your own judgement

| Gate | Trigger |
|---|---|
| ADR-045 acceptance | drafted → operator's explicit word, then a Status-flipping commit |
| R6 reading | the sanitizer result → present with the acceptance question |
| NO-GO | no patchable line AND R3 fails → the ADR-041 V7 conversation |
| B0 spend | any new run → surface the remaining-hours arithmetic first |
| B3 ceiling | operator-only, before B2 is filled |
| Destructive / non-aero LXC / burst tier / RunPod ledger | propose-first, literal `approved` |

HARD DON'TS — these have all bitten already

- **Never cancel a self-hosted CI job** to free a runner; it strands detached solves.
- **Never `run_long.sh wait`** — `AERO_RUN_LONG_REAP=1` makes wait the OWNER and kills the run.
- Never relax a pre-registered band, and never widen Q1's 2 %/5 %/5 % for a new purpose.
- Never write a value into a provenance-bearing field you have not actually computed.
- `.venv` on PATH or pre-commit silently rolls back; **`git log` after every commit**;
  commits are `<type>(stage-20): …`; commit messages with quotes go through a heredoc.
- The provenance guard refuses a dirty tree before a run. Commit first. That is correct.
- Untouchable artefacts: stage20-screen{,9}, the I4 pair `-20260810-1447*`, the Q1 pair
  `*-20260812-2159*`, both N3 attempt-1 runs, both N3 attempt-2 runs, the mining dir,
  and `hg2007_flexible_foil-20260912-161321` (it is R3's control).
- Keep the handoff and RESUME current **as you go, not at the end**. Status stays
  `partial`; no tag, no verdict.

Final state each session: clean tree, pushed, PR #44 checks green,
`pytest -q tests/unit tests/stage_20` green, nothing running on aero-dev you did not intend.
