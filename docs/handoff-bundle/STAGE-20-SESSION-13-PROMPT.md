Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). Resuming a partial stage,
session 13. Repo /root/projects/aero-research-platform, branch
stage-20-flexible-flapping-wing-fsi (tip = latest on the branch — verify with git log;
session 12's record is ab0509a, this prompt's add-commit a4c5866), PR #44 (draft),
962 tests green + 2
pre-existing skips (`PATH="$PWD/.venv/bin:$PATH" pytest -q tests/unit tests/stage_20`),
mypy clean on aero/, tree clean, pushed. aero-dev is IDLE, nothing is running anywhere,
and **N3 is NOT running — session 12 deliberately did not resubmit it.**

READ FIRST, IN THIS ORDER — all of them, before writing anything:

1. CLAUDE.md and .aero-stage (still 20, do not bump).
2. docs/handoff-bundle/STAGE-20-RESUME.md — §6h (session 12's summary) and the §7
   START-HERE header.
3. docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md — §6.46-§6.49 and
   §7's SESSION-13 RESUMPTION PATH. **§6.48 corrects §6.46/§6.47 (read those two THROUGH
   it), and §6.49 corrects two readings made around §6.46: "345.9 was unprecedented" is
   refuted, and "Courant 0.549 at death" was the t=0 startup value (death-step 0.1139).**
4. ADR-040 (accepted, add-commit d5bf381) and ADR-039 (accepted, FROZEN, digest-pinned;
   its <<B2-PENDING-I4>> stands unfilled PERMANENTLY). Naming collision: "ADR-039 N3" (a
   wave-1 contingency) and "N3" (the confirmation probe) are different objects with one
   name — qualify every cross-ADR reference.
5. The session-12 mining evidence: /mnt/aero-nfs/runs/stage20-n3-attempt1-mining/README.md,
   then minerA_flexible.tsv, minerB_flexible.tsv, minerD_flexible.tsv,
   minerF_determinism.txt as needed. The tables AND the exact parsers are there; the run
   dirs themselves are untouched.
6. The machinery — ALL EXISTS AND IS TESTED, reuse, never rebuild:
   scripts/stage20_hg2007_flexible_foil.py (--probe/--collect-probe/--project-n3/--status/
   --size-040/--submit-040/--record-* modes; --submit refuses forever);
   aero/vv/fsi/hg2007_sizing.py (N3Confirmation, size_gated_campaign_040,
   i7_probe_from_bundle, n3_confirmation_from_bundle); aero/adapters/precice/schedule.py
   (the window-index join); aero/adapters/precice/{launcher,case,template}.py (where the
   coupling-scheme work lands); scripts/run_long.sh (status/logs/kill; NEVER wait —
   AERO_RUN_LONG_REAP=1 makes wait the OWNER and kills the run).

STATE — what is settled; do not re-derive, do not re-litigate:

- **Session 12's mining verdict is MITIGATION-WARRANTED (§6.49), adversarially verified,
  zero unresolved refutations.** The N3 flexible abort has a ~150-window precursor: a
  period-2 ODD-window instability inside CalculiX from ~window 1557 — odd-window absolute
  residuals 34.8 → 1665.4 N doubling every ~26 windows while EVEN windows decrease
  (commanded amplitude grew only 1.19x — not load tracking); ccx Newton effort escalates
  on the same odd windows (39 windows ≥ 8 iters, all odd, unbroken 1625..1701); the
  residual argmax marches into the death cluster (strict share 0 % → 6 % → 67 %). The
  interface is BLIND to all of it (preCICE coupling health, fluid series, interface
  forces all clean). Proximate killer: CalculiX-2.20-internal heap corruption, timing-
  sensitive (Q1 was sicker in coupling health and died of nothing).
- **Determinism is DIVERGENT** (byte-identical decks split at the first parallel GAMG
  solve), so an unmitigated re-run is NOT a sharp reproduce/not-reproduce probe. §6.48's
  "reproducibility is itself the discriminating measurement" rationale is dead.
- **The instability set in at 0.27 % of full commanded amplitude.** If it is a real
  property of this configuration, the 1.17 M-window campaign at full amplitude cannot run
  unmitigated regardless of the memory bug.
- **The operator endorsed the ladder path at session-12 close-out**: one mitigation ADR
  (ADR-041) pre-registering a short diagnostic ladder, the ladder picks the mitigation,
  Q1 re-runs on the winner, then N3. The ADR TEXT still needs operator acceptance before
  anything runs — that gate is real, do not skip it.
- Budget: **B0 has 134 h remaining** (122 531 s of 604 800 consumed; 96 h per-submission
  ceiling untouched). Projected spend: ladder ~6-18 h + Q1 ~1 h + N3 ~82 h ≈ inside B0
  with margin. Wave 1's W6 protection is untouched (W6 governs wave-1 solves only).
- Q1's ACCEPT applies to the UNMITIGATED stack only. Any adopted mitigation moves the
  config it certified, so **Q1 must be re-run on the mitigated stack before N3** (same
  frozen bands; W4 applies if it rejects).
- B1/B2/B3 keep their sentinels, the four GATED_040_* are None, and
  data/vv/stage20_n3_confirmation.json still does NOT exist.
- tests/unit/test_n3_live_submission_digest_is_pinned.py stays until N3 is collected;
  **any spec change re-pins it in the same commit** (new digests replace bfc60a49…/
  ed1ba571…); delete it only after N3 is collected (§6.44).

YOUR TASK, IN THIS ORDER (handoff §7 SESSION-13 path + the endorsed ladder):

1. Cheap re-verification: NFS mounted, aero-dev idle (exact-name pgrep — `pgrep -f` on
   the solver names matches its own ssh command line and false-positives), suite green at
   ab0509a or later. Do not re-discover the homelab.
2. **Draft ADR-041 — mitigation pre-registration.** Evidence base: handoff §6.49 + the
   NFS mining dir. Pre-register: the diagnostic ladder (below), the ADOPTION RULE (the
   campaign takes the CHEAPEST rung that eliminates the precursor signature over the
   probe span — no odd/even residual divergence, stationary envelopes), and the recorded
   consequences per rung: deck bytes and preCICE config each move the spec config_hash
   (ADR-037 precedent), a ccx build change moves the container SHA (P1/P3), Q1 was
   measured on the unmitigated stack, digest re-pin in the same commit. Ladder:
   - D-A: UNMITIGATED flexible arm + hash-exempt observability armed — the solid-side
     absolute-residual watchdog (threshold ~10x the baseline ceiling 44.3 N ≈ 443 N —
     would have fired ~w1650), core-dump ulimit, MALLOC_CHECK_ in the environment.
     Establishes recurrence + onset variability; a core names the corruption site.
   - D-B: serial-implicit coupling (the period-2 odd/even split with a clean interface is
     the classic parallel-implicit signature; I10's 99.4 % fluid-CPU share means the
     sequential solid adds little — the rung MEASURES the cost instead of assuming it).
   - D-C (fallback, only if D-B fails): ccx *CONTROLS/damping deck bytes, or the heavier
     CalculiX 2.21/2.22 build bump (new container pin, re-opens I9 conventions).
   Probe span: **8000 windows (0.16 s — round-trips .13e, verified), flexible arm only,
   uncontended** — diagnosis needs no contention and these probes can NEVER size anything;
   say so in the records. 4000 (0.08 s) is the verified cheap fallback; **6000 does NOT
   round-trip** — do not use it. Expect ~3-9 h per rung.
   **STOP: bring the operator the ADR-041 text and wait for acceptance before any
   implementation lands or any probe runs.**
3. After acceptance: implement behind tests, in this order — the watchdog (repo-side,
   reads Solid.log, hash-exempt, becomes part of ALL future polling), the D-A env
   observability, the serial-implicit knob through the spec (it must NOT be able to claim
   the gated verdict — L5's five-input derivation stays authoritative; a mitigated config
   becomes the campaign config only via the ADR + re-pin). Commit ADR-041 + knobs +
   re-pinned digests together where the spec moves.
4. Run the ladder on aero-dev, detached, one rung at a time (D-A, then D-B; D-C only per
   the ADR's rule). Poll read-only; watchdog armed. Evaluate per the pre-registered
   adoption rule. **If NO rung eliminates the precursor: STOP — that is the
   NO-GO-on-infrastructure conversation, and a recorded NO-GO is a legitimate outcome.**
5. Q1 re-run on the adopted stack (both arms concurrently, 500 windows, ~45 min, frozen
   bands verbatim, --record-q1). If it rejects, W4 applies — stop and bring the operator
   the choice it names.
6. **Re-run N3, both arms, contended, detached** (an ordinary B0 probe):
   python scripts/stage20_hg2007_flexible_foil.py --probe flexible mid --probe-dt 2e-5 \
     --probe-windows 76090 --ranks 4 --numerics adr040-candidate --timeout 345600 --out <f>
   and the rigid mirror, submitted concurrently — adjusting --numerics/knobs to the
   ADOPTED stack exactly as ADR-041 registers it. **Three argparse defaults silently
   sabotage the run if omitted: --timeout (43 200), --numerics (adr039-baseline),
   --ranks (1).** Copy both submission JSONs to
   /mnt/aero-nfs/runs/<run_id>/n3-submission.json immediately. SUBMIT ONLY — record
   session names + poll commands in the handoff in the same sitting. Stop rule stands:
   one arm dies pre-ramp (window 50 725) ⇒ `run_long.sh kill root@aero-dev <session>` the
   partner and record both. Poll with run_long.sh status + --project-n3 (read-only); the
   ramp clears ~52 h in. NEVER run_long.sh wait.
7. While N3 burns: local work only — NOTHING else may run on aero-dev (contention
   purity). Keep the handoff + RESUME current as you go, not at the end.
8. After N3 lands: unchanged downstream — --collect-probe both arms → the fine-rung I7
   probe (alone, same dt, must COMPLETE all-exited, ≥ 50 726 windows, use 76090,
   multi-day at 130 032 cells) → bring the operator the measured post-ramp rate and take
   the **B3 ceiling decision BEFORE B2 is filled** → --size-040 <flex> <rigid> <fine>
   --ceiling-s <approved> → fill B1/B2/B3 + the four GATED_040_* in the commit that ADDS
   data/vv/stage20_n3_confirmation.json (never an overwrite; _merge_base_guard_040
   resolves add-commits; ADR-040's is d5bf381) with
   tests/unit/test_adr040_budget_is_derived_from_n3.py re-deriving the numbers → wave 1
   via --submit-040, submit only. RECOMMENDED to the operator before wave 1:
   /code-review ultra 44 (user-triggered, billed — the agent cannot launch it).

Say in the handoff UP FRONT: items 6-8 will very likely NOT all land this session. The
realistic deliverable is ADR-041 accepted, the ladder run with a recorded verdict, Q1
re-measured on the winner, and N3 resubmitted with the stop rule armed.

HARD-WON SPECIFICS THAT WILL BITE:
- Do not change ANYTHING that moves the HG spec's config_hash while a run is live —
  _reattach refuses to collect a submission whose spec no longer rebuilds to its digest.
- Window counts must survive float(format(n*dt,'.13e')) == n*dt: 8000 and 4000 verified
  OK, 6000 fails, 50 725 fails, 50 726/76 090 OK, 76 125 famously fails.
- Under mpirun, ExecutionTime is RANK 0's CPU — rates come from ClockTime. Time dirs sit
  at processor*/<time> (the collector is rank-aware at maxdepth 4).
- ccx's .cvg RESID.FORCE is a PERCENTAGE normalized by near-zero early-ramp average force
  — absolute residuals live only in Solid.log. preCICE lines carry ANSI escape bytes
  (LC_ALL=C, grep -a, regex match, never fixed fields). .cvg/.sta repeat INC once per
  coupling iteration — group by INC.
- ADR-039's block and every test on it stay byte-untouched; ADR-040's contingencies are
  W-prefixed; qualify every cross-ADR reference ("ADR-039 N3").
- Pre-commit needs the venv on PATH or the hooks SILENTLY roll the commit back —
  PATH="$PWD/.venv/bin:$PATH" git commit, and git log after EVERY commit. Never
  hand-expand an abbreviated sha — git rev-parse.
- NEVER cancel a self-hosted CI job — it strands detached solves.
- Artefacts to leave alone: /mnt/aero-nfs/runs/stage20-screen{,9}, the I4 pair
  hg2007_*_foil-20260810-1447*, the Q1 pair *-20260812-2159*, BOTH N3 attempt-1 runs, and
  the mining evidence dir stage20-n3-attempt1-mining/. e1b35b5 stays parked on
  docs/atlas-pointer.
- The RunPod ledger fix (/etc/aero/runpod-ledger.json cap_usd 9.0 → 150.0, inert but
  stale) is still propose-first; apply only on the operator's literal `approved`.

Auto-mode: proceed without approval prompts, announce actions; stop for: ADR-041
acceptance (step 2's gate), a ladder that eliminates nothing (the NO-GO conversation), a
Q1 rejection (W4), destructive ops, the B3 ceiling decision, the burst cost tier, and
non-aero LXCs.

Keep BOTH the handoff and STAGE-20-RESUME.md current as you go. Status stays `partial`;
no tag and no verdict until an ADR-040-sized campaign has run and the driver's
clause-by-clause verdict exists.
