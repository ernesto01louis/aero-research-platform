Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). Resuming a partial stage,
session 15. Repo /root/projects/aero-research-platform, branch
stage-20-flexible-flapping-wing-fsi (tip = latest on the branch — verify with git log),
PR #44 (draft), **1056 tests green + 3 pre-existing skips**
(`PATH="$PWD/.venv/bin:$PATH" pytest -q tests/unit tests/stage_20`), mypy clean on aero/,
tree clean, pushed.

**Nothing is running on aero-dev.** The sanitizer hunt LANDED and was read (§6.76);
**ADR-045 is ACCEPTED as amended A1–A15 (§6.78)**; C2/C3, C7, C1 and C6 are in code
(§6.79–§6.80). **C5 is BUILT (§6.81): `calculix-precice-adr045.sif` is the solid container of record.**
**One thing waits on the operator's word: R3's calibration finding (§6.79)** — two draws of
the same submission differ over windows 4001–8000 by more than Q1b's band, so R3(a) as
pre-registered cannot be passed; four options are put, the agent recommends restarting at
w400 where the signal resolves. Nothing is submitted until it is answered.

FIRST COMMAND, BEFORE ANYTHING ELSE — the box must be idle, and the decision state read:

    ssh root@aero-dev 'pgrep -x pimpleFoam; pgrep -x ccx_preCICE; pgrep -x mpirun; true'
    sed -n '3,6p' docs/adrs/ADR-045-checkpoint-restart-for-the-coupled-flexible-arm.md
    python3 -c "import json;r=json.load(open('/mnt/aero-nfs/runs/hg2007_flexible_foil-20260915-113918/asan-hunt-verdict.json'));print(r['verdict'],r['windows_reached'],r['participants'])"

The Status line says `accepted`. If the operator has NOT answered §6.79 (R3) and §6.80
(the build), there is no run to submit and no container to build: local work only.

READ FIRST, IN THIS ORDER — all of them, before writing anything:

1. CLAUDE.md and .aero-stage (still 20, do not bump).
2. docs/handoff-bundle/STAGE-20-RESUME.md — **§6z (session 14), §6x (ADR-045), §6w (the
   hunt, landed)**, then §6v, §6u, §6t. §6z is the one that matters today.
3. docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md — **§6.75 (the
   reader, and the NINE measured corrections to ADR-045's proposed text), §6.76 (the hunt's
   reading and why silence is not exoneration), §6.77 (the decision memo)**, then §6.71–6.74.
4. **docs/adrs/ADR-045-checkpoint-restart-for-the-coupled-flexible-arm.md — still
   PROPOSED.** Read it whole; R6's SECOND bullet is now the operative clause; §6.75's table
   is what an acceptance commit must carry as amendments.
5. ADR-041 (V7 = the NO-GO clause), ADR-043, ADR-044. ADR-039/040 FROZEN; FORBIDDEN lists
   carry over unconditionally.
6. The session-14 plan `/root/.claude/plans/stage-20-flexible-parsed-sonnet.md` — Phase C
   (C0–C8) is the implementation map IF accepted; its ⚠ hazards were measured, not guessed.

STATE — settled; do not re-derive, do not re-litigate:

- **The hunt's reading is `no-report-died` and it is NOT exoneration.**
  `fsi-hg2007_flexible_foil-20260915-113918` died at window 2 369 of 8 000 after 2.87 h of
  CalculiX's own `solution seems to diverge` stop (rc=201, `checkconvergence.c:587` →
  `stop.f:25`), with zero `asan-solid.*` files. The ADR-041 detector read PRECURSOR on it
  (parity ratio 59.8): the UNMITIGATED period-2 mode ran to a Newton-divergence abort before
  any heap corruption fired. It outlived three of the five earlier death windows; SPOOLES,
  ARPACK, libprecice, MPI and libgfortran are uninstrumented, so a store inside them is
  invisible to ASan and lands in a redzone, not glibc's chunk header (hypothesis). Two
  independent readers of the raw files agree. Record:
  `/mnt/aero-nfs/runs/hg2007_flexible_foil-20260915-113918/asan-hunt-verdict.json`.
- **No patchable line exists.** R6 bullet 1 is not available; upstream v2.20.2 already
  carries the "different invalid free" (#173); nothing newer upstream touches code.
- **The reader is code**: `aero/adapters/precice/asan.py`, `asan_hunt_verdict`,
  `--asan-evaluate` (`84a4c08`, 39 tests, reviewed adversarially). Re-run it, never re-read
  by eye alone.
- **ADR-045's proposed text has nine measured errors or silences** (handoff §6.75 table).
  The ones that bite: `config_hash` does NOT move on a deck edit (bump `RENDERER_VERSION`);
  R7's gate hook cannot sit in the spec-derived `gated` while `restart_generations` stays
  out of `spec_knobs`; R5's energy band spans 3.7 decades; `decomposePar -force` deletes
  the fluid's checkpoints so a relaunch cannot use the submit path; `precice-run/` removal
  is already the supervisor's; `stage16_urans_cert.py` is the restart precedent.
- **B0 has ~76 h left.** A third N3 attempt needs ~74 h. ADR-045 R3's treatment needs ~3 h,
  but only AFTER C1–C7 (adapter C, deck + renderer bump + re-pin, container rebuild,
  relaunch driver, R5 guard, R3 scorer) — which cost no B0.
- Q1 PASSED on the adopted stack; the digest pins name N3 attempt 2; `<<B2-PENDING-I4>>`
  stands unfilled permanently. Nothing has been resubmitted.

YOUR TASK, IN THIS ORDER

1. Run the FIRST COMMAND block. Read the operator's answer to §6.79 (R3's clause). The
   build is done and recorded (§6.81). With R3's option chosen: amend the ADR
   (an amendment commit BEFORE the treatment), then C8 behind the B0 gate — segment 1 =
   the identical 8000-window submission on the new SIF with `--ckpt-at` covering the
   restart window, killed once the checkpoint and the fluid dump exist; segment 2 =
   `--restart`; then `--score-r3 --out data/vv/stage20_adr045_r3.json`.
2. **The acceptance is done; the text below is what an acceptance would have required:** the acceptance commit flips the Status line AND records
   the nine §6.75 corrections as amendments in the ADR text (the ADR-044 `d702b57`
   pattern: Status hunk + body amendments, Date line unchanged). Then Phase C in clause
   order, each commit suite-green, `git log` after each: C1 adapter C (patch file under
   `containers/`, applied after the `git checkout` in the Dockerfile; rotate the preCICE
   logs on restart), C2 deck `TIME=TOTAL TIME` + `RENDERER_VERSION` bump + same-commit
   re-pin, C3 `writePrecision`, C4 R5 guard (phase-aware energy bound), C5 container
   rebuild (propose-first), C6 relaunch driver + top-level `restart_generations` + a
   collect-side gate, **C7 the R3 scorer BEFORE the treatment (control vs itself must
   pass; the band mapping shown to the operator)**, C8 the treatment — **B0 stop gate:
   surface the arithmetic first**. R3 fails ⇒ NO-GO (ADR-041 V7), recorded, no sixth lever.
3. **If DECLINED:** record the NO-GO on infrastructure per ADR-041 V7 in the handoff and
   RESUME (a result, not a failure); status stays `partial`; no run; the reader, the
   records and the corrections stay as evidence.
4. **If AMENDED:** revise the ADR text as the operator says; it stays `proposed` until the
   explicit word.
5. Keep the handoff and RESUME current as you go.

STOP GATES — present and wait; do not proceed on your own judgement

| Gate | Trigger |
|---|---|
| ADR-045 acceptance | operator's explicit word → a Status-flipping commit carrying the amendments |
| B0 spend | any new run → surface the remaining-hours arithmetic first (~76 h) |
| NO-GO | ADR-045 declined, or R3 fails → the ADR-041 V7 conversation |
| Container rebuild | propose-first; `scripts/build_calculix_sif.sh` on the host + aero-build |
| B3 ceiling | operator-only, before B2 is filled |
| Destructive / non-aero LXC / burst tier / RunPod ledger | propose-first, literal `approved` |

HARD DON'TS — these have all bitten already

- **Never cancel a self-hosted CI job**; **never `run_long.sh wait`**.
- Never relax a pre-registered band; never widen Q1's 2 %/5 %/5 %.
- Never write a value into a provenance-bearing field you have not computed.
- `.venv` on PATH for every commit; **`git log` after every commit**; `<type>(stage-20): …`;
  quotes in commit messages go through a heredoc. **The pre-commit pytest hook stashes
  unstaged changes** — a commit whose tests import an unstaged module is refused (bit
  session 14); stage what a commit's tests need, or commit code and tests together.
- The provenance guard refuses a dirty tree before a run. Commit first.
- Untouchable artefacts: stage20-screen{,9}, the I4 pair `-20260810-1447*`, the Q1 pair
  `*-20260812-2159*`, both N3 attempt-1 runs, both N3 attempt-2 runs, the mining dir,
  `hg2007_flexible_foil-20260912-161321` (R3's control), and now the hunt
  `hg2007_flexible_foil-20260915-113918` and its sibling `-113507` (the reader's fixtures).
- Do not re-run the hunt, and do not build a wider one, without an ADR: "no sixth lever".
- Status stays `partial`; no tag, no verdict.

Final state each session: clean tree, pushed, PR #44 checks green,
`pytest -q tests/unit tests/stage_20` green, nothing running on aero-dev you did not intend.
