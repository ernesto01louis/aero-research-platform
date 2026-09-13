---
stage: 20
stage_name: "Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul)"
status: partial
date_started: 2026-07-30
date_completed: 2026-08-13
session_duration_hours: 31
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5[1m]
git_sha_start: 42ebb55e984f6762e982d358678c443c857b6dce
git_sha_end: c77447558f6a307e64a254eeb78743c53cde48a9
stage_tag: v0.0.20
next_stage: 21
next_stage_name: "Stage 21 — Release (v0.1.0)"
---

# Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul) — PARTIAL 2026-07-30

> **Read this first. Status: PARTIAL, and deliberately so — no tag.** The foundation phases are
> done and verified; the authored case, the pre-registration and the campaign are not started.
> **No gated claim has been made and none may be, because ADR-039 does not exist yet.** Nothing
> here is a Stage-20 verdict.

## 0. The one-paragraph version

The two hard structural problems are solved. **CalculiX is genuinely in the loop**: the
perpendicular-flap smoke ran OpenFOAM in `precice-fsi.sif` and CalculiX in
`calculix-precice.sif`, 50/50 coupled windows converged at a mean of 2.14 iterations, both
participants exited 0, and the flap tip deflected 0 → 0.1646 m under a real fluid force of
~8.6 N. That is two-way FSI across two containers, which nothing before this had shown — Stage 19
put both participants in one image. And **the multi-container provenance question is decided**
(ADR-038): `ProvenanceTuple` carries a `containers` roster, strictly additively, so a gated
two-SIF run is now expressible; Stage 19's blanket refusal is replaced by
`assert_provenance_describes`, which enforces the property that actually matters. The
Heathcote-Gursul reference is acquired to the extent the prose supports exactly, including
author-stated measurement uncertainties. What remains is the largest single chunk — authoring the
coupled case — plus the pre-registration and a multi-day campaign.

## 1. Deliverables status

*Current as of the end of session 4 (2026-08-04). Verified against the tree, not against
the prose — every ❌ below was confirmed by `ls`.*

| # | Deliverable (verbatim from the stage prompt) | Status | What exists / what does not |
|---|---|:-:|---|
| 1 | CalculiX in the loop — `.inp` writer, adapter `config.yml`, element choice | ✅ | **Smoke PASSES on two containers** (upstream's bytes, `a9a2355`); element choice settled by evidence (§6.1). Writers landed session 5; the solver's authored branch landed session 6 (`227ffed`) and the case materializes end to end — 18 files, every one re-read, schema-v2 manifest |
| 2 | The Heathcote-Gursul case in `aero/vv/fsi/` + DVC reference data | ✅ | **Reference COMPLETE**: text-sourced exact, 208 markers digitized, `hg2007_recomputed.csv` written, R2 passes, operating point fixed (§7.1), two corrections landed (§6.6, §6.7). `aero/vv/fsi/{hg2007_flexible_foil,hg2007_readout}.py` landed session 6 (`21840e0`); both arms registered in all three `FSI_CASES` sites' source of truth |
| 3 | Pre-registered gate block (ADR-039) before any campaign run | ⚠️ | **ADR-039 EXISTS and is frozen** (session 7, `94c2b98`): 58 clauses across ten families, byte-duplicated in the campaign driver, binding tests in `tests/unit/`, B2 carrying `<<B2-PENDING-I4>>` + the committed pure sizing rule. **B2 cannot honestly be filled**: the pre-flight measured the pre-registered configuration infeasible by 1-2 orders of magnitude (§6.29) and the sizing rule refuses by design |
| 4 | Flexible-vs-rigid delta with `compose_improvement()` | ⚠️ | Every input exists and is measured per arm (`ArmReadout` carries the per-cycle series the paired estimator needs). `align_arms` was hardened in session 6 (§6.23). The composition itself is the campaign driver's and lands with ADR-039 |
| 5 | Provenance for a genuinely two-container run | ✅ | **ADR-038 `accepted` 2026-08-06.** Both residuals closed in session 6: the CLI derives the SIFs from the spec and calls `assert_provenance_describes` (`7f1d584`), and a per-CASE stage/solver-version override stops a Stage-20 bundle claiming a Nutils solid |
| 6 | ADRs; GO/NO-GO; handoff; tag `v0.0.20` | ⚠️ | ADR-037/038 `accepted`; **ADR-039 `accepted` (session 7)**; this handoff; **no tag, no verdict**. The gated sentinels remain `None` — structurally correct, because the pre-flight found the pre-registered campaign does not fit its own ceilings (§6.29). The resumption path is an ADR-040 re-pre-registration (§7 item 1), honest because **no gated campaign ever ran** |

**Session 5 (2026-08-05) moves deliverables 1 and 4 substantially.** Every writer and reader
the authored case needs now exists and is tested; what is left of deliverable 1 is *wiring*
(the solver's authored materialization branch), not authorship. Deliverable 4's machinery —
the paired path — is now callable, which it provably was not before. Details in §3 and §6.17-§6.21.

**Session 6 (2026-08-06) closes deliverables 1, 2 and 5.** The authored case **materializes end
to end** (`227ffed`): `_materialize` and `_render_manifest` no longer raise, an authored spec
writes 18 files under `<root>/<case_dir_name>/`, every one is re-read, and the schema-v2
manifest binds `spec_sha256` to the digest `config_hash` will compute. **`aero/vv/fsi/` now
holds the Heathcote-Gursul case** (`21840e0`) — both arms registered, the band-less predicate
registry, and a readout that structurally cannot skip the gates. Two silent-wrong-number
defects were fixed on the way (§6.22, §6.23), one of them found by the adversarial review
this stage had been carrying as an open item. **Phase 3D wired the CLI** (`7f1d584`), which
closed ADR-038's live residual — `assert_provenance_describes` had zero call sites — and
stopped a Stage-20 bundle claiming a Nutils solid. **ADR-037 written and ADR-038 ratified**
(`d6f0b99`). Suite **581 → 672**, mypy clean, seven commits `227ffed`..`d6f0b99`.
**What remains: ADR-039, the pre-flight, and the campaign.**

**Session 7 (2026-08-10) freezes the pre-registration, hardens three modules against
thirteen review candidates, builds the detached campaign seam — and the pre-flight then
finds the pre-registered campaign infeasible before a single wave burned.** ADR-039
landed with `<<B2-PENDING-I4>>` (`94c2b98`), the driver byte-duplicates it with
submit-detached/collect/verdict modes and the additive launcher seam (`a0312e1`), and
eleven of the resumed adversarial review's fourteen candidates were verified and fixed
(`b222c18`, `94c3306`) — three of them silent-wrong-number defects in the GATED readout.
The pre-flight then ran in leverage order: I7's candidate dt FAILED Co <= 1 at window 1
(measured 9.61, §6.29), the rule-suggested dt passes Courant (0.549) but prices the
campaign at 1-2 orders of magnitude over the frozen ceilings, and the committed sizing
rule refuses to size — so `GATED_TIME_WINDOW_S`/`GATED_MAX_TIME_S` remain `None`, no
wave launched, and the structural guarantee did exactly what it was built to do.
Suite 672 → 726 (mypy clean repo-wide); e1b35b5 rebased off the branch (preserved on `docs/atlas-pointer`,
§3). **What remains: an ADR-040 re-pre-registration informed by §6.29's measurements
(§7 item 1), then the campaign.**

**Enabling work not on the deliverable list, done in session 4 because everything above
depends on it:** the `source` seam under `CoupledCaseSpec` (`1bd7011` — an authored case
had nowhere to live), the additive `PreciceConfigExpectation` extension (`10fcb70` —
the C-family claim was not expressible), and the `transient_fvschemes` byte pin
(`c682671` — the pin the plan relied on did not exist). Suite 348 → **418**.

## 2. Decisions made

- **Extend `ProvenanceTuple`, not hash a container set** (ADR-038, operator-chosen). A composite
  digest resolves to nothing in `containers/SHA256SUMS`, so inverting it needs a side manifest plus
  its own CI check — the same surface arrived at indirectly — and it silently redefines
  `container_sif_sha256` for a subset of runs while leaving the field name and type identical. The
  roster says what happened instead of encoding it. Strictly additive: existing field unchanged,
  new field defaults empty, fifth MLflow tag only when non-empty, nullable Postgres column.
- **The gated-multi-SIF refusal is replaced, not deleted.** `CoupledCaseSpec` only ever knew SIF
  *names*, so it could enforce a proxy at best. `assert_provenance_describes(spec, provenance)`
  enforces the real property — a run's provenance must name every SIF it runs — at the point the
  digests exist.
- **Run the smoke on upstream's bytes verbatim.** The point of the smoke is to learn the
  `ccx_preCICE` conventions the authored case must reproduce; learning them from a case we wrote
  would be circular. It paid immediately (§6.1).
- **A separate tutorial archive, not an extended one.** The Stage-19 archive's sha256 is
  `TutorialPin.archive_sha256` in the FSI3 spec and its manifest backs a closed, tagged verdict.
  Extending it — the obvious shortcut — would have changed that digest and retroactively
  invalidated the Stage-19 record.
- **Treat ssh rc 255 as a transport fault on the exit code alone**, not on a stderr pattern. The
  failure that motivated the fix arrived as rc 255 with an **empty stderr**, so a pattern match
  would have missed exactly the case it was written for. The message says it is a hint, not a
  verdict.
- **Do not publish a half-done digitization.** The text-sourced values are exact and committed; the
  figure-read values are not, and are marked as pending rather than estimated. See §6.2 for why
  this specific reference has earned that caution.

**Session 4 (2026-08-04) — four operator decisions, all of which belong in ADR-039**

- **Time scheme: `backward` IF AND ONLY IF checkpoint fidelity is proved; otherwise `Euler`.**
  Every preCICE OpenFOAM tutorial, including the perpendicular-flap bytes, uses `Euler`. Second
  order in time under *implicit* coupling requires the adapter to checkpoint and restore
  `U.oldTime().oldTime()` on every coupling iteration, and nothing in this repo establishes that
  the pinned adapter does. If it does not, `backward` is silently first-order-plus-noise and the
  record would carry a temporal-accuracy claim it does not have. The probe becomes a **reusable
  pre-flight clause I8** in `aero/vv/` — 5 windows implicit versus the same 5 at
  `max-iterations 1`, comparing window-start field state — not a throwaway spike, so any future
  preCICE stage inherits it. Either way the claim is measured. *(Note the counter-argument that
  makes `Euler` defensible if I8 fails: the fixed coupling time-window-size across all rungs makes
  temporal error common-mode, so it does not contaminate the spatial GCI.)*
- **`NLGEOM` ON unconditionally.** The honest model for a plate deflecting 73x its own thickness,
  even though upstream's proven `flap.inp` omits it at a *larger* 16 % tip deflection and the
  geometric correction at our 5.35 deg is ~0.15 % — three orders inside D0's 0.25 band. B2 is sized
  for whatever it costs; the Newton-loop multiplier over ~70 000 increments is unmeasured on this
  box and I4 must report it.
- **D9 is REPORTED-ONLY; D10 stays gated.** D9 pre-registered `|P2-P1|/P1 <= 0.005` on the rigid
  arm while D8 separately *admits* up to 2 deg of pitch there. At 2 deg the TE's extra velocity is
  `0.060 m x 0.0349 rad x 6.194 rad/s = 0.0130 m/s` against an LE velocity amplitude of
  `a*omega = 0.1084 m/s` — **12 %** — and P1 assumes a single rigid-body velocity. D8 and D9 could
  not both be satisfiable in the worst admissible case, so a D9 NO-GO would have said nothing about
  the physics. `(P1-P2)/P2` is now reported on **both** arms as the measured bias the naive formula
  would have injected. D10 (`|P3-P2|/P2 <= 2 %`) remains in the VERDICT line: it is a genuine
  closure identity with no rigid-body assumption.
- **Budget fallback: raise the ceiling, do not degrade the evidence.** If I7 fixes `dt` and I4 then
  projects wave 1 past its ceiling, the pre-registered response is (1) **per-wave ceiling raised to
  14 days** and (2) **wave 1 reordered to the rung carrying the paired increment, both arms**, with
  wave 2 the two GCI-only rungs — so an overrun costs the GCI term, never the headline increment.
  Cutting settled cycles below 10 and accepting a budget NO-GO are the declared last resorts, in
  that order, and only if 14 days per wave is also exceeded. aero-dev is otherwise idle, so wall
  clock is the cheapest thing to spend.

**Session 7 (2026-08-10) — decisions**

- **e1b35b5 off the branch before pushing.** `commit-lint.yml` requires a `stage-NN`
  scope on EVERY PR commit; the unscoped atlas commit would have flipped PR #44 red.
  Rebased out (both commits were local-only, no force-push), preserved verbatim on
  branch `docs/atlas-pointer` for the operator to land wherever it belongs.
- **The review's fourteen candidates were verified by hand** after the refuters died on
  a usage limit a second time — dispositions in §6.26, all BEFORE ADR-039 froze.
- **I7 is a cycle-scale COUPLED probe, not "a few fluid-only steps"**: no fluid-only
  vehicle exists (the authored controlDict carries the adapter FO with `errors strict`),
  and the (1-cos) ramp spans a full cycle so a short probe measures the wrong regime.
- **dt fixed across rungs** (the I8 common-mode rationale beats §6.11's scaled-dt
  sketch), which is why I7 also demands a fine-rung Courant measurement.
- **B2's projection uses the contention-measured rate** — the mid-rung probes run both
  arms concurrently, the wave-1 shape.
- **ddt = Euler** (I8 measured; §6.29 note 2 and `data/vv/stage20_i8_checkpoint.json`):
  the probe bounds the checkpoint discrepancy at coupling-tolerance scale but cannot
  prove round-off fidelity, and the frozen rule demands proof for `backward`.
- **The stuck probes were killed, the wave was NOT launched.** A probe that structurally
  cannot finish inside its frozen ceiling records nothing further by burning 12 h; the
  500-window calibrations it was replaced by satisfy I4's own completion criterion. No
  gated wave launched because the sizing rule refuses — the system, not discipline.

## 3. Deviations from the stage plan

- **The stage is incomplete.** The approved plan costed the campaign alone at ~5-7 days of
  aero-dev wall clock (3 rungs × 2 arms, operator-chosen), on top of authoring a coupled case that
  has no upstream equivalent. One session was never going to reach a verdict; this handoff records
  where it actually got to.
- **Figure digitization deferred within Phase 2.** Planned as part of acquisition. The text-sourced
  half is exact and done; the figure half is specified but not executed (§7 item 1).
- **The plan's plane-stress element recommendation is superseded** by what the smoke showed
  (§6.1). Evidence over plan — which is why the smoke was sequenced first.

**Session 3 (2026-08-01) — deviations, and why**

- **Only Phase 3A's first half landed.** The two non-regression pins and their goldens are
  committed (`67d8e82`); the refactor they exist to protect is not, nor is anything after it.
  The ordering rule ("land the tests on pre-refactor code, see them green, THEN refactor") is the
  stage's single most important one, and half of it done correctly is worth more than both halves
  done in the wrong order. What is left is enumerated in §7 item 3b.
- **The campaign as scoped does not fit its ceiling, and this was found before the ADR froze
  rather than after** (§6.11). Two operator decisions followed — the settled-cycle ladder with two
  launch waves, and pre-registering the sizing *rule* with B2's numbers filled from I4 in a later
  commit. Both are deviations from the resume prompt's "6 runs launched concurrently" and from
  ADR-036's precedent of concrete numbers in B2; both are recorded here and belong in ADR-039.
- **A new pre-flight clause, I7,** is proposed ahead of ADR-039: a measured max-Courant probe. The
  prompt lists I1/I3/I4/I5/I6 only. Without it the B-family would be pre-registered against an
  estimate, and §6.11 shows the estimate spans an order of magnitude.
- **`PreciceConfigExpectation` needs an additive extension** it was not scoped for, or the
  C-family's "every rendered token is observable in the parsed model" cannot be honoured (§6.12).
- **Two repo-hygiene carve-outs were added** (`.gitignore` negation, `end-of-file-fixer` exclude).
  Both change shared config to protect a fixture, so they are called out rather than buried: see
  §6.10 for why renaming the fixtures instead would have made them stop testing anything.

**Session 4 (2026-08-04) — deviations, and why**

- **Phase 3A landed as specified; Phase 3B is one commit of three.** Three commits landed
  (`1bd7011`, `10fcb70`, `c682671`), suite 380 -> 418 green, mypy clean. The session did not reach
  the authored writers, the ADRs, pre-flight or the campaign. What was done was done to the
  standard the stage demands rather than more of it done thinly — the precedent of sessions 2
  and 3.
- **`MaterializedTree` carries ONE `source` field, not the `pin` XOR `authored` pair every prior
  prompt and plan specified.** This is a deliberate departure with a demonstrated cause: pydantic's
  `model_copy(update=...)` **bypasses** `@model_validator(mode="after")` even on a frozen,
  `validate_assignment=True` model (verified in-process, and pinned by a test), and `case.py`
  mutates trees with exactly that idiom in two places. The XOR would have been enforced only at
  construction and forgeable by any helper written by analogy. See §6.14.
- **A `transient_fvschemes` byte pin had to be invented before `ddt_scheme=` could be added**
  (§6.15). The prompt cites a pin that does not exist. Landing it consumed a commit that was not
  in the plan, and it is the Phase-3A ordering rule applied a second time.
- **The I3/I5 static baseline was measured EARLY, out of the prompt's order.** It needs no new
  code, costs ~15 minutes, and it invalidates two numbers the stage would otherwise have
  pre-registered against. See §6.16. Measuring it before the ADR freezes is the whole point of
  I-family clauses.
- **`85e0b32` was already recorded in §4** by session 3; the resume prompt's instruction to add it
  was stale. No change needed.
- **`_SOLVER_SIF["precice"] -> both SIFs` is not expressible** and Phase 3D must not attempt it:
  the dict is `dict[str, str]` feeding a single-SIF `compute_provenance`. The container of record
  and the extras are already on `CoupledCaseSpec` (`container_of_record`, `extra_container_sifs`),
  so the CLI must derive them from the spec, not widen the table.

**Session 5 (2026-08-05) — deviations, and why**

- **Phases 3B and 3C landed except the solver's authored-materialization branch and the V&V
  case object (C13/C14).** Ten commits, `397af1c`..`b9f317f`, suite 418 → **581**. Every
  writer and reader exists, each with its own re-reader or assertion; what does not exist is
  the code that CALLS them from `PreciceCoupledSolver._materialize`, which still raises for
  an authored source. That is the next commit and it is fully specified — see §7 item 4b.
- **Three pre-flight probes were pulled forward, out of the prompt's order** (S1, I6, and
  most of I3), for the reason session 4 gave for measuring I3/I5 early: each one could have
  invalidated something the ADRs would otherwise pre-register. All three changed the code
  or the record — see §6.17, §6.19, §6.21. This is the same "measure before the ADR freezes"
  discipline, applied three more times.
- **`farfield_extent_chords` is 20, not the 100 §6.16's control implicitly used** (§6.21).
  A deliberate choice with a measured consequence, recorded rather than absorbed.
- **The Proxmox host rebooted mid-session.** Nothing was lost: all ten commits were already
  pushed, the one uncommitted file was intact, aero-dev came back with the NFS mount healthy
  and no stranded solves, and the two-container smoke re-passed on a clean tree. The only
  casualty was an in-flight background review, which produced no findings and was not
  re-run.
- **No adversarial review pass was completed this session.** One was launched and died with
  the host. Carried as an open item (§7 item 7) rather than quietly dropped.

**Session 6 (2026-08-06) — deviations, and why**

- **Four commits, and two of them are defect fixes that were not in the plan.** The session's
  plan was materialization → V&V case → CLI → ADRs. The adversarial review (carried since
  session 5 as open item 7) and a design-validation pass together surfaced thirteen defects,
  three of the silent-wrong-number class. Two were in code the next commits would immediately
  depend on, so they were fixed first rather than recorded and deferred: §6.22 (the fluid and
  solid readers kept DIFFERENT coupling iterates) and §6.23 (an `AlignedPair` could attest to
  a time base it never compared). Both would have produced plausible numbers in the gated
  increment.
- **The adversarial review ran only partially.** 25 of 79 agents completed before the run hit
  a usage limit; the `template.py` and `calculix.py` refuter panels — the two blind spots
  handoff §7 item 7 names — died with it, and the synthesis stage never ran. What survived is
  one defect confirmed by six independent refuter votes across two lenses (§6.23). **The two
  named blind spots remain unreviewed** and are carried forward in §7 item 7.
- **The pre-flight and the campaign did not start.** The session went into materialization,
  the case object and the two defect fixes instead. That is the sessions-2-through-5 precedent
  — the work that was done was done to the standard the stage demands rather than more of it
  done thinly — and it means ADR-037/038/039 and every I-clause are still ahead.
- **`n_samples` on `AlignedPair` is now `int | None`, and `AlignedPair` gained two fields.**
  A schema change to a model landed in session 5, made deliberately rather than absorbed:
  the field could not distinguish a verified pair from an unverified one, which is the one
  thing the object exists to do. See §6.23.
- **`tests/stage_20` is NOT in CI** (§6.24). Discovered while deciding where ADR-039's binding
  tests go. Not fixed in-stage — the ADR-039 tests will live in `tests/unit/` beside
  `test_stage19_gate_block_sync.py`, which is where the Stage-19 precedent already puts them —
  and carried in the ledger.

**Session 7 (2026-08-10) — deviations, and why**

- **The gate block is 271 lines against ADR-036's measured 150.** Ten families and 58
  clauses against eight and ~30; every extra line is a clause or its rationale, not
  padding. The binding tests assert the byte SHAPE (width, indents, ASCII), not a count.
- **ADR-039's C2 was corrected one commit after it landed** (`a0312e1`): the block said
  the INC margin was 10x while `94c3306` had already hardened the code to 50x. The code
  was stricter than the block, never looser; both copies now state 50, and the
  correction rode in the same commit as the byte-identical driver copy.
- **I1's dummies ran in one SIF** — measured: `calculix-precice.sif` ships no pyprecice
  (§6.27). The cross-SIF property is carried by the same-day smoke.
- **The fine-rung probe and the coarse/fine calibrations were NOT run.** The budget
  conclusion is rung-independent (§6.29: mid misses by >= 20x; coarse is ~1.7x cheaper
  per window) — a declared bounded-coverage decision, not an oversight.
- **B1 was set at 172800 s with a 43200 s per-submission ceiling** (the prompt's floor
  was 21600 s): B1 froze before I7 ran and the probes were known to be cycle-scale.
  Even so, the 1.5-period probe at the Courant-passing dt does not fit — that finding
  IS §6.29.
- **N3 declares one resubmission on participant-died**, a recorded deviation from
  ADR-036's no-restart rule, argued from the 14-day exposure (a died run carries no
  gated numbers to retry). Unused this session.

## 4. Environment / dependency / schema changes

- `ProvenanceTuple` gains `containers: tuple[ContainerRef, ...] = ()` and a fifth conditional
  MLflow tag `container_sif_set`. `ContainerRef` and `container_roster` are new public names.
- **Postgres: migration `005_container_set`** adds a nullable `container_sif_set TEXT` to
  `mlflow_artifact_provenance` plus a partial index. **APPLIED 2026-07-31** by the operator from
  the Proxmox host (`alembic upgrade head`); `alembic current` reports `005_container_set (head)`.
  Verified after the fact rather than assumed: the column is `text`/nullable, all **1280**
  historical rows are intact with `container_sif_set IS NULL` (correct — every pre-Stage-20 run is
  single-container), and both the old and new indexes are present.
  **The mirror write path is verified too**, inside a transaction that was rolled back: the real
  `_INSERT_SQL` accepts a two-container roster, the stored value is byte-identical to the
  `container_sif_set` MLflow tag, and it round-trips back to both SIF digests. Row count unchanged.
  *(Note the DB is at 192.168.2.184; CT 202 is its CTID, not its address.)*
- `ExecResult` gains `transport_error` / `transport_failed`; `MeshHandle` gains `failure`;
  `aero.orchestration.describe_failure` is new.
- New pytest marker `stage_20`; new test dir `tests/stage_20/`. Suite is **418 green**
  (`pytest -q tests/unit tests/stage_20`), up from 348 at Stage-19 close (380 after session 3).
- **New module `aero/adapters/precice/manifest.py`** — the two `aero-manifest.json` renderers,
  schema v1 (tutorial) and v2 (authored), as free functions over primitives. Stdlib only; it is
  transitively imported by `aero.adapters.precice` and pulls in no banned module (verified).
- `CoupledCaseSpec` loses five fields to `source`; `TutorialTree` is renamed `MaterializedTree`;
  `TutorialSource` / `AuthoredSource` / `CASE_ROOT_DIRNAME` are new public names.
  `PreciceConfigExpectation` gains 15 optional fields plus the `UNSET` sentinel, and
  `MeshExpectation` / `ParticipantDataExpectation` / `MappingExpectation` are new public models.
- **`85e0b32` (operator, 2026-07-31) — `run_long.sh`: a timed-out wait no longer strands the solve
  it was watching.** `cmd_wait` counted only its own sleeps, ignoring the ~0.5 s ssh round trip per
  poll, so a nominal 14400 s ceiling did not fire until ~15800 s while `LocalSSHExecutor` guarded
  the subprocess at `timeout_s + 120`. The guard therefore ALWAYS won the race, SIGKILLed the
  script before its reap branch, and `AERO_RUN_LONG_REAP=1` never ran — "decorative on the one path
  it was written for" (moving-vv run 30615205786 left `pimpleFoam` running on aero-dev). Fixed two
  ways on purpose: `cmd_wait` now measures a real clock (`date +%s`), and the executor reaps for
  itself in its own `TimeoutExpired` branch via the new named `_WAIT_GUARD_MARGIN_S`.
  **This matters directly for a six-run concurrent campaign** — six detached solves, six waits.
- New fixture trees `tests/stage_20/fixtures/{stage19_load_path,materialization}/`, and two
  `.pre-commit-config.yaml` / `.gitignore` carve-outs they need (§6.10).
- New reference dirs `data/references/fsi/{heathcote_gursul_2007,precice_perpendicular_flap}/`.
  The perpendicular-flap archive is DVC-tracked and pushed to `aero-minio`
  (sha256 `6f1c7b9b0b849845…`, 170 files, same pin `cd33e2db` as Stage 19).
- `CONSTITUTION.md` Invariant 3 item 3 **clarified** (not amended in substance): the rule is
  unchanged — four tags, same shape — only the description widens to name the container of record
  and point at the roster.

## 5. CI/CD changes

- **No new workflows, no new required checks.** `vv-required`'s paths filter already covers
  `aero/adapters/**` and `aero/vv/**`.
- All 10 host-side required checks are green on PR #44 (draft).
- The `stage_20` unit tests ride the existing required `pytest unit (py3.12)` job.

## 6. Gotchas discovered

### 6.1 Upstream's 2-D CalculiX idiom is a 3-D slab, not plane stress

`perpendicular-flap/solid-calculix/all.msh` is a **one-element-thick 3-D mesh** (z ∈ {0, 1}) of
**`C3D8I`** elements (738 nodes, 244 elements), with `*BOUNDARY Nall, 3` suppressing the
out-of-plane dof, while both preCICE meshes are declared `dimensions="2"`. The plan had
recommended CalculiX plane-stress (`CPS8R`) elements; upstream's own proven idiom is the slab.
**Use the slab, and use `C3D8I`** — the incompatible-modes hex is what cures shear locking in a
thin bending member, which is exactly the HG plate's regime, and it is what the calculix-adapter is
actually exercised against.

Also learned, and all needed by the Stage-20 deck writer:

- the adapter's `config.yml` `patch:` name maps to an `*NSET` with an `N` prefix
  (`patch: surface` → `*NSET,NSET=Nsurface`);
- the adapter injects forces by **overwriting a `*CLOAD` block** the deck declares as zeros on the
  interface node set — the deck must declare it or there is nothing to overwrite;
- the calculix-adapter reads **`Force`**, not FSI3's `Stress` — that difference belongs in the
  C-family of the gate block;
- upstream's coupling numerics for this class: `parallel-implicit`, `max-iterations 50`, relative
  5e-3 on **both** `Displacement` and `Force`, IQN-ILS with QR2 filter, `initial-relaxation 0.5`,
  `time-windows-reused 15`;
- the OpenFOAM side needs `preciceDict` with `locations faceCenters` and a dimensioned `rho`.

### 6.2 The reference has two live traps, both recorded before use

**Figures 5.6 and 5.1 plot `C_T/St²`, not `C_T`** — despite Figure 5.6's caption reading "Thrust
coefficient as a function of Strouhal number". At St = 0.3 that is a factor of **11.1**. And there
are **three** Heathcote experiments that are easy to conflate: this one (chordwise flexibility,
teardrop + steel plate, 90 mm chord, thesis Ch. 5 = the AIAA-J 2007 paper); the repo's existing
`plunging_airfoil_hg2007` (rigid NACA-0012, thesis Fig 2.9); and Heathcote, Wang & Gursul 2008
(spanwise flexibility, NACA-0012, 100 mm chord). The existing file's own `⚠️ CORRECTION` section
records that its values were once wrong by 3-5× — thrust digitized off the efficiency curve.

### 6.3 `u95_input` here is measured, not estimated

The thesis states its own instrument uncertainty: **≈5 % on thrust**, **≈10 % on efficiency**
(the latter because efficiency uses gauge readings in both directions), with a component
breakdown. That is far better evidence than a digitization guess, and it is what should flow into
`compose_reportable`/`compose_improvement`.

**The increment's `u95_input` is legitimately smaller than the absolutes'**: both points are read
off the *same figure with the same axes* and measured on the *same gauge with the same
calibration*, so the axis-calibration and systematic terms largely cancel in the difference. That
must be *shown* in `digitization.csv`, not asserted.

### 6.4 An unreachable host used to read as "blockMesh failed"

`moving-vv` run 30568971572 died in 18 s because the CI runner cannot resolve `aero-dev`. ssh
returned 255, `OpenFOAMSolver.mesh` logged only `returncode` and `stdout`, and
`BenchmarkRunner._drive` raised a hard-coded `"blockMesh failed"` — the message also named
`blockMesh` for pipelines running four or five utilities. Fixed; `ExecResult.transport_failed`
distinguishes "the command never ran" from "the command ran and failed".

### 6.5 The ruff-format pre-commit hook rolls commits back silently

Observed three times this session: hooks reformat, the commit does not land, and the shell shows
no obvious failure. **Run `git log` after every commit.** Running
`ruff format && ruff check --fix` before `git add` avoids it.

### 6.6 The recorded thesis sha256 was never reproducible — and neither is any raw PDF digest here

Bath's Pure repository **re-wraps the PDF on every download** with `OpenPDF 1.4.2`. Two fetches of
the same URL, minutes apart, differ in exactly **60 bytes of 12,175,275** — the `/CreationDate`
stamp and the `/ID` trailer array. Every content stream is byte-identical. So `fdee2ce4…`, recorded
2026-07-30, was a per-fetch artifact, and this reference's claim that the figure render was
"reproducible from the recorded PDF digest" was **false as written**.

Replaced by two invariants, both verified across independent fetches: a **content digest**
(`276cec6e…`, `/ID` + dates normalized) and a **per-page 200 dpi raster digest** under a pinned
`pymupdf==1.26.3`. The raster digest is the stronger one — it pins the exact pixels that were read.
**Generalise this:** any digest of a document fetched from a repository that stamps downloads is
worthless as a reproducibility anchor. Check before recording one.

### 6.7 The plunge amplitude in `reference.md` was wrong — `h = 0.194`, not 0.175

§2.1.4 fixes `a = 17.5 mm` for **every** water-tunnel run, and this airfoil's chord is 90 mm, so
`h = a/c = 0.194` — which is how the thesis writes it dozens of times through Chapters 3–5.
`h = 0.175` belongs to the **other two** Heathcote experiments: the NACA-0012 validation model
(p78) and the **spanwise** wing, where `h = a_ROOT/c = 0.175` because that chord is 100 mm. Same
shaker amplitude, different chord. That is precisely the three-way conflation the reference file's
own opening callout warns about — and the file had made it. 11 % on the plunge amplitude, which
propagates into the frequency-from-Strouhal conversion, the mesh-motion probe, and every solve.

### 6.8 This thesis's blanket "for all Reynolds numbers" prose does not survive its own figures

§5.3.2 states the rigid drag→thrust transition is at "St=0.17" and holds "for all Reynolds
numbers" (§5.3.3 repeats it for efficiency). Figure 5.6 gives **0.191 / 0.161 / 0.167** at
Re = 9000 / 18000 / 27000. Two of three reproduce it; **Re = 9000 — the gated Re — is +12.6 %**.

The digitization is not at fault: per-panel calibration is verified three independent ways, and
Fig 5.9a corroborates Re = 9000 independently (negative-efficiency points "are not shown", and the
rigid efficiency series begins at St = 0.205 with nothing below it). At 9× magnification there is
no marker hidden on the zero line — the crossing is genuinely unmarked.

**The lesson generalises past this anchor.** A blanket "for all Re" statement in this thesis is a
rounded generalisation, not a measurement. Its *condition-specific* prose is a different and much
stronger class of claim — the 6°/17° pitch amplitudes, each tied to a named foil and a named St,
reproduce to **0.1 %**. Weight them accordingly. R2 gates the crossover only where prose and
figure agree; the measured Re = 9000 value is carried as a row in the reference of record.

### 6.9 The C-grid's non-orthogonality has always been ~85, so I5 cannot use an absolute threshold

The mesh spike measured max non-orthogonality of **84.9** for the HG section, **80.5** for a stock
NACA 0012 at identical knobs, and **86.5** for the platform's own default Stage-05 production V&V
mesh — the one every TMR run uses. It barely moves with far-field extent (20/50/100 c), normal
count (80/120/140) or first-cell height (2e-6/1e-5/1e-4 c), and the **average is only ~18**. It is
a localised property of this C-grid family and always has been; the HG section adds ~4°.

So ADR-024's absolute `non-ortho ≤ 70`, applied to I5, **would fail on the static mesh before any
motion** — and would equally fail the platform's production V&V mesh. ADR-024's 70 was measured on
the *flapping-wing* writer, a different mesh. **I5 must gate the DEGRADATION under motion against
the recorded static baseline**, plus absolute skewness ≤ 4 and zero negative volumes — which is
what ADR-024's real failure mode looked like anyway (skewness 5503, 18 145 inverted pyramids):
catastrophic, not marginal. Write that into ADR-039 rather than inheriting the number.

Also note `MeshQualityGate`'s M2 = 65 default was authored in Stage 18 for the **snappy** path and
has never been applied to the blockMesh C-grid. Applying it now would be a new, retroactive gate.

### 6.10 Four traps in the Stage-19 non-regression fixtures, all found by writing them

The two pins landed at `67d8e82` (`tests/stage_20/test_stage19_{load_path_unchanged,
materialization_is_byte_identical}.py`). Each of these would have produced a *green* or
*absent* test rather than a loud one:

- **`load()` emits 23 scalars, not 20.** The resume prompt says 20. A golden written against
  "20 scalars" would have passed vacuously. The test spells all 23 out as a literal.
- **`*.log` is gitignored repo-wide** (`.gitignore:60`), and the fixture's filenames are load
  bearing — `find_iterations_logs` globs `precice-*-iterations.log`, `watchpoint_path` builds
  `precice-<Participant>-watchpoint-<name>.log`. The fixture would have been committed incomplete
  and CI would have failed on a missing file, not on a wrong number. Scoped negation added.
- **`end-of-file-fixer` was appending a newline to those fixtures.** preCICE's `TXTTableWriter`
  PREFIXES each row with `"\n"`, so its files genuinely end without one, and `_txt_table` relies
  on that to spot a partially-written final row. The hook is now scoped away from them rather than
  the fixtures being made unfaithful.
- **`tarfile.extractall` chowns every member when running as root** (with `-1/-1`, because the
  `data` filter strips recorded ownership), so a monkeypatched `os.chown` sees far more than
  `_chown_tree`'s calls. Discriminate on the uid. The property actually worth pinning — chown
  after digest verification, *before* the manifest write — is observable as `aero-manifest.json`
  being absent from the call list, which needs no real inode and so works on a CI runner.

`.within()`'s window scoping is verified by **mutation, not assumption**: neutering
`CouplingIterationReport.within` makes `load()` raise on the fixture. And the K1 unification the
refactor performs is **provably a no-op on the tagged Stage-19 record** —
`data/vv/stage19_turek_hron_fsi3.json` reports `n_nonconverged: 0` over 8000/8000 windows for both
participants, so whole-run and window-scoped agree there. Record that in ADR-037; it is the
evidence that makes the behaviour change safe rather than merely plausible.

### 6.11 The flexible plate is the clock, and the default wall spacing is unrunnable

Two mesh facts decide the campaign's wall time, and neither is in the plan:

- **`CaseSpec.first_cell_height` defaults to `2.0e-6` chords** (`schemas.py:176`) — 0.18 µm on a
  90 mm chord, authored for a y+<1 RAS TMR mesh. The wake-cut block inherits it, and the transverse
  velocity there is the full plunge speed, so `Co <= 1` would need `dt ~ 1.7e-6 s`. **The mesh
  spike used this default**, so its 48 240 cells / skew 2.40 numbers describe a mesh nobody can
  integrate at a fixed time step. `PlungingAirfoilSpec` already uses **`5.0e-4`** (Stage-11/13
  precedent) — that is the value to pre-register, and I3/I5 must re-measure the static baseline
  with it.
- **The C-grid's surface blocks are `simpleGrading (1.0 …)`** (`case_writer.py:209-216`), i.e.
  UNIFORM in arc length — the cosine-spaced control points are shape fidelity, not the cell
  distribution. That is what makes a Courant estimate tractable at all, and it had not been
  written down anywhere.

With those, the binding limiter is the **blunt-TE base of the flexible plate**: 76.5 µm across
`n_te` cells. At `n_te = 2` that is 38 µm against a peak plunge velocity `a*omega = 0.1084 m/s`
(1.08 U), giving `dt ~ 3.5e-4 s` — **5x tighter than the rigid arm**, which the paired A-family
forces both arms to share. At `T = 1.0145 s` that is ~2900 windows/cycle; 24 cycles is ~70 000
windows, and the finest rung (dt scaled by the refinement ratio) ~90 000. **The campaign does not
fit a 7-day ceiling on the central estimate** (fine rung ~8.3 d), and the plausible band is wide.

Two operator decisions were taken on this, both to be written into ADR-039:

1. **Settled-cycle ladder plus two launch waves** — >=20 settled cycles on the rung carrying the
   paired increment, >=10 on the GCI-only rungs (`DEFAULT_MIN_SAMPLES` is 8, so 10 is a declared
   margin, and a GCI needs converged *means*, not tight variances); wave 1 = coarse+mid, wave 2 =
   fine, with the 7-day ceiling applying **per wave**.
2. **Pre-register the sizing RULE, not the numbers.** ADR-039 lands complete with B2 carrying the
   rule plus a `<<B2-PENDING-I4>>` marker; the I4/I7 record lands next with its own four-fold
   tuple; a third commit fills the marker only, and a committed pure sizing function plus a test
   re-derive the numbers from the I4 JSON so they are an output rather than a decision. The driver
   refuses a gated run unless `git merge-base --is-ancestor` proves ADR-039's first commit precedes
   the I4 record.

Add **I7**, a cheap measured max-Courant probe (a few fluid-only steps at the candidate `deltaT`
with the mesh at mid-stroke), and run it **before** ADR-039 freezes, so the arithmetic above
becomes a measurement rather than an estimate. Pre-flight FAILS on `Co > 1`; it never adjusts.

### 6.12 Three things in the authored case that fail silently, not loudly

Found by reading upstream's actual `perpendicular-flap/solid-calculix/flap.inp` bytes:

- **The CalculiX slab's z-thickness must equal the OpenFOAM `span`.** preCICE `Force` is an
  absolute force in newtons. Upstream's flap gets away with a `z in {0,1}` slab because its fluid
  span is also 1. The HG fluid span is 2.5 mm (`tests/stage_20/test_hg_section.py`), so a 1 m slab
  under-loads the plate by 400x: `checkMesh` is fine, the coupling converges, and the pitch
  amplitude just comes out at 0.01 degrees. One `span` field must feed both writers, with a
  C-family clause asserting the emitted `.inp` z-extent equals the emitted `blockMeshDict` span.
- **`*STEP, INC=1000000`.** CalculiX's default is 100. At `INC=100` with tens of thousands of
  windows ccx finishes its step, writes its `.frd` and exits **0**; `read_coupled_status` reads rc 0
  as `exited-ok`, `stopped_by` becomes `all-exited`, and **K2 passes**. The failure only surfaces
  at S3, after the fluid has burned its ceiling.
- **`PreciceConfigExpectation` has no field for the RBF `support-radius`** or for any acceleration
  parameter (`config.py:536-557`), even though `MappingDecl.support_radius` and the
  `AccelerationDecl` fields are all parsed. So "assert every rendered token is observable in the
  parsed model" is **not achievable through `assert_config` as it stands** — it needs an additive
  extension (`| None = None` fields, so FSI3's expectation and its tests stay byte-identical).
  Upstream's `support-radius="1."` is one metre on a 0.09 m chord and must be scaled.

Also settled by reading those bytes: `*BOUNDARY Nall, 3` gives plane **strain**, so the effective
modulus is `E/(1-nu^2) = 2.253e11`, not 2.05e11 — the naive `Eb^3/12` hand-check is otherwise 10 %
off. And with `ALPHA=0.0` and no damping, the cycle-mean reaction power over the prescribed region
equals the interface power exactly, which is what makes D10 a real closure check *and* a check
that `ALPHA=0` held.

### 6.13 The ADR-039 bands, computed — and the floor binds on four of five

Applying the pre-registered rule `4 x (u95_ref/|value|)`, floored 0.25, capped 0.50, to
`hg2007_recomputed.csv` (instrument systematic 5 % thrust / 10 % efficiency on **absolute** rows
only; increments use the reading terms alone, which is what the CSV's `u_axis_abs = 0` encodes):

| clause | quantity | value | `u95_ref` | raw 4x | band | binding |
|---|---|---|---|---|---|---|
| D0 | pitch amplitude, flexible | 5.34637 deg | 0.08651 | 0.065 | **0.25** | floor |
| D1 | `C_T` flexible | 1.00772 | 0.05187 | 0.206 | **0.25** | floor |
| D2 | `eta` flexible | 0.175279 | 0.01756 | 0.401 | **0.40** | — |
| D3 | `dC_T` | 0.609257 | 0.00325 | 0.021 | **0.25** | floor |
| D4 | `d eta` | 0.0865273 | 0.0 | 0.0 | **0.25** | floor |

**The cap never binds; the floor binds four times out of five, so for D3 and D4 the 4x rule is
decorative and 0.25 is a policy number.** Say that in the ADR rather than letting the formula imply
the band was derived. It matters: ADR-022 measured this platform's 2-D plunging solve missing HG's
absolute rigid thrust by -28 %/+58 %, and if that error is multiplicative and common-mode the
increment inherits ~28 % — **a NO-GO on D3 is at least as likely as one on D1**.

Two structural notes for the same section. `MetricSpec` only expresses relative/absolute/normalized
numeric bands, so D5/D6 (signs) and D7 (admissibility) have to be structural predicates carrying a
literal `(no band)` token, while D8 (rigid pitch <= 2 deg), D9 and D10 ride the existing harness as
`comparison="absolute"` against a reference of `0.0` with the power *ratios* emitted into
`solve.scalars`. And ADR-036's band-parity regex `r"^\s+(D\d) [^\n]*within (\d+) %"` has three
defects for Stage 20: `D\d` matches **`D10` as `D1`** (a phantom pair, silently), `(\d+) %` cannot
express D9's 0.5 %, and `^\s+` also matches five-space continuation lines.

### 6.14 A nullable XOR pair is forgeable, because `model_copy` skips after-validators

Every prior Stage-20 plan specified `MaterializedTree` (was `TutorialTree`) as carrying `pin` XOR
`authored`, with `write_manifest` dispatching on `pin is not None`. That shape is unsound here.
Verified in-process on a frozen, `extra="forbid"`, `validate_assignment=True` model with an
`@model_validator(mode="after")` enforcing the XOR:

    m = M(a=1)                      -> a=1 b=None
    m.model_copy(update={"b": 2})   -> a=1 b=2      # the validator did NOT run

and `case.py` builds trees with `tree.model_copy(update={"mutations": ...})` in **both**
`select_fluid_mesh` (`:392`) and `record_max_time_mutation` (`:415`). So the invariant would have
held only at construction, and any authored-path helper written by analogy with those two — the
obvious thing for the next session to write — could produce a both-set tree.

**What that costs, concretely.** A both-set tree takes the `pin is not None` branch and emits a
**schema-v1 tutorial manifest for a case we authored**: a `"pin"` block naming
`precice/tutorials @ cd33e2db` beside bytes this platform wrote, with every authored-provenance
key silently dropped. That manifest ships in the bundle. Nothing raises. A reviewer reads it as
"this run laid down the pinned upstream tutorial". It is a provenance lie produced by a runtime
predicate — the exact class of failure the Phase-3A discipline exists to prevent.

**The fix removes the predicate.** One `source: TutorialSource | AuthoredSource` field on the tree;
both emitters are free functions in a new `aero/adapters/precice/manifest.py`; and `_write_case`
selects between them by an exhaustive `match spec.source.kind` with `assert_never`, so a third
source type in a future stage is a **type error** rather than a silent fall-through. There is no
invariant left to forge. Generalise it: *any* invariant expressed only as an after-validator is
bypassable in a codebase that uses `model_copy(update=...)` at all.

### 6.15 The `transient_fvschemes` byte pin the prompt relies on does not exist

`tests/stage_11/test_dynamic_mesh_writers.py:62` is

    assert (tmp_path / "system" / "fvSchemes").read_text() == fc.transient_fvschemes()

Both sides call the same function. It pins writer/consumer **agreement** — that the cylinder writer
really renders the shared helper — and nothing about the bytes. Change the default output and both
sides move together; the test stays green. `grep -rn "1df84e21" tests/` returns nothing.

Measured on pre-change code, and now pinned as literals in
`tests/stage_20/test_fvschemes_bytes_before_ddt_scheme.py`:

| turbulence model | length | sha256 |
|---|---:|---|
| `laminar` (the default) | **781** | `1df84e211d7836d8fe9b7b935f5cd4af339174ef3c0d8aacc84b190c0678e4ef` |
| `kOmegaSST` | 886 | `4edd1332bf0bba804327e9e52dd3f6c0c1100e45ea040404b5ad5908b3d4c302` |
| `kOmegaSSTLM` | 958 | `3703fe5ca9f6735f404d1a4df3d2e7fc607063c772872ca9f219e3f841fc0f90` |

Without it, a mistake in a new `ddt_scheme=` default branch would silently rewrite the `fvSchemes`
of the Stage-10 static cylinder, the Stage-11 plunging foil and the Stage-13 URANS decks —
invalidating the records those decks produced, with nothing going red. The pin lives in
`tests/stage_20/` on purpose: `tests/stage_11/` is **not** in the mandated
`pytest -q tests/unit tests/stage_20` suite.

### 6.16 I3/I5 measured: the failing checkMesh check is ASPECT RATIO, not non-orthogonality —
### and it fails identically on the platform's own stock NACA 0012

Re-measured on aero-dev at the **pre-registered** `first_cell_height = 5.0e-4 c` (the spike's
numbers came from the `2.0e-6` default and do not apply), both arms, three candidate rungs, span
slab 2.5 mm. Every number recorded, passing or not:

| rung | arm | cells | nonOrtho max | skew max | aspect ratio | min vol | neg vols | `Mesh OK` |
|---|---|---:|---:|---:|---:|---:|:-:|:-:|
| fine | flexible | 130 032 | 86.315 | 1.768 | 1847.56 | 2.466e-12 | no | **no** |
| fine | rigid | 130 032 | 86.317 | 1.767 | 1847.56 | 2.462e-12 | no | **no** |
| mid | flexible | 77 240 | 85.230 | 2.163 | 1884.45 | 4.133e-12 | no | **no** |
| mid | rigid | 77 240 | 85.233 | 2.162 | 1884.45 | 4.127e-12 | no | **no** |
| coarse | flexible | 45 682 | 85.650 | 2.555 | 1914.12 | 6.968e-12 | no | **no** |
| coarse | rigid | 45 682 | 85.651 | 2.554 | 1914.12 | 6.958e-12 | no | **no** |

Controls, at the mid rung and identical knobs:

| variant | cells | nonOrtho | skew | aspect ratio | `Mesh OK` |
|---|---:|---:|---:|---:|:-:|
| **stock NACA 0012**, 5.0e-4 | 76 896 | 82.565 | 1.998 | **1884.4471** | **no** |
| HG flexible, 5.0e-4 | 77 240 | 85.230 | 2.163 | **1884.4471** | no |
| HG flexible, 2.0e-6 (the spike's mesh) | 77 240 | 87.288 | 2.322 | 2954.45 | no |

Five things follow, and three of them change what ADR-039 may say:

1. **checkMesh's own non-orthogonality check reports "Non-orthogonality check OK" at 85.23.** The
   one failing check is `***High aspect ratio cells found, Max aspect ratio: 1884.4471, number of
   cells 2892`. §6.9 reached the right conclusion about I5 for a slightly wrong reason.
2. **The aspect ratio is byte-identical (1884.4471) between the HG section and the stock NACA
   0012.** It is a pre-existing property of the platform's own eight-block C-grid family, in the
   far field, untouched by the surface curve. Stage 20 did not introduce it.
3. **`MeshQualityGate`'s M1 ("Mesh OK") therefore cannot be an absolute I5 gate either** — it fails
   on the platform's own stock airfoil mesh at the pre-registered spacing. This extends §6.9's
   argument from M2 to M1, now with a control. I5 gates **degradation against the recorded static
   baseline** plus absolute skew <= 4 and zero negative volumes; **M1 and M2 are reported, never
   gated**, and the ADR must say why with these numbers beside it.
4. **The pre-registered spacing is better on every metric than the spike's**: non-ortho
   87.29 -> 85.23, skew 2.32 -> 2.16, aspect ratio 2954 -> 1884. Changing it was not only necessary
   for the time step, it improved the mesh.
5. **The rung ladder is clean.** Cell counts 45 682 / 77 240 / 130 032 give
   `sqrt(77240/45682) = 1.300` and `sqrt(130032/77240) = 1.298` — a uniform 2-D refinement ratio of
   1.30 across both steps, which is what a three-grid GCI wants. Knobs, built downward:
   fine `(n_surface, n_normal, n_front, n_wake, n_te) = (140, 140, 70, 112, 6)`,
   mid `(108, 108, 54, 86, 4)`, coarse `(83, 83, 42, 66, 3)`.
   The two arms differ only in the 5th significant figure of every quality metric, so the paired
   increment is not confounded by mesh quality.

Raw JSON for both probes is in the session scratchpad; it must be re-run by the I3/I5 pre-flight
into `data/vv/` with its own four-fold tuple before ADR-039 cites it. **These numbers are a
measurement, not yet a record.**

### 6.17 CalculiX truncates every numeric field at 20 characters — full precision cannot ride in a deck

The solid deck was first written at `%.16e` (22 characters). ccx 2.20 rejected **every
numeric card it read** — `*NODE`, `*ELASTIC`, `*DENSITY`, `*AMPLITUDE`, `*DYNAMIC` — with
`*ERROR reading ...` and rc=201, before a single increment. It reads reals as `(1:20)`, so
a wider field is truncated mid-number. At `%.13e` (19 characters, 14 significant digits)
the identical deck reads, solves and exits 0 in 2.7 s.

**A double needs 17 significant digits and does not fit**, once a sign and a negative
exponent are there. So the deck writer splits the difference by ORIGIN: values the campaign
*chooses* (`time_window_size`, `max_time`, `span`) must be exactly representable — a spec
validator refuses them otherwise, which keeps the "solid dt equals the coupling window"
assertion exact and costs nothing, because those numbers are picked and picking a round one
is free. Values the geometry *derives* (node coordinates, amplitude rows) cannot be chosen,
so they are asserted to 1e-12 m — eleven orders below the 76.5 µm plate.

Generalise it: **any writer for a fixed-format solver input needs its precision measured,
not assumed**, and the check belongs in the writer (`_num` refuses a too-wide field) rather
than in a reviewer's eye.

### 6.18 A 70 005-row `*AMPLITUDE` table is fine

The campaign samples the prescribed plunge once per coupling window, which at the candidate
`dt` is ~70 000 rows. ccx reads it without complaint: rc=0, ~2.9 s including 100 increments.
So the S1 question "is there an `*AMPLITUDE` row limit" is answered — **not at this scale** —
and the per-window sampling can stay, which matters because rows placed exactly where a
`*DYNAMIC, DIRECT` step evaluates its boundary conditions make the interpolation error at
the evaluation points zero rather than merely bounded.

### 6.19 The `.dat` is a four-line record, not a table — and the coded FO compiles

Both learned by running, both needed by the readout.

`*NODE PRINT, NSET=Nnose, TOTALS=ONLY` + `RF` emits, per increment:

    <blank>
     total force (fx,fy,fz) for set NNOSE and time  0.5000000E-02
    <blank>
           -6.391247E-10  6.290534E-06 -7.841086E-16

Note the time is printed at **seven significant digits**, so a record cannot be compared
bitwise against the coupling schedule; `ccx_dat.assert_matches_schedule` maps onto window
indices with a tolerance derived from that precision. Ten records of the real file are
committed as a test fixture (`tests/stage_20/fixtures/ccx_dat/`) — a reader tested only
against bytes its own test generates proves nothing but self-consistency.

**The coded interface-power function object compiles and runs** under
`setpriv --reuid 1000` (I6, brought forward). Its summed force reproduces `force.dat`'s
total to **twelve significant figures**, and on a stationary mesh the power comes out at
−4.3e-18 — the null result that proves it reads the *wall* velocity rather than a
cell-centre one.

### 6.20 The limit-cycle analysis had to expose per-cycle objects, and anchoring them is subtle

`paired_delta_uncertainty` needs a `CycleSamples` and a `CycleConvergenceReport` per arm;
`analyse_limit_cycle` computed both and discarded them, so the paired path could not be
CALLED. Exposing them was the easy half.

The hard half: they must be anchored at the **post-discard origin**, not at the settled
tail. The estimator checks `report.n_cycles` against `samples.n_cycles` and applies the
converged-from offset *itself*. A tail-anchored series fails that check whenever the tail
starts after cycle 0 and — if the lengths ever coincided — would apply the offset twice,
pairing cycle *k* of one arm against a different physical cycle of the other. **The first
version of this commit had it wrong and every test passed**, because every fixture was a
limit cycle from its first sample, so `converged_from_cycle` was 0 and the two anchorings
coincided. A fixture with a real transient is what catches it. Generalise: *a fixture with
no transient cannot test transient-dependent indexing.*

Two smaller measured facts from the same work. A perfectly noiseless synthetic record makes
the per-cycle difference series exactly constant, and the batch-means estimator **refuses**
it ("not a real limit cycle") — correctly; a credible fixture must carry variance. And an
exponential transient with too long a time constant leaves enough residual that the
CUMULATIVE drift bound refuses the record outright, so a settling fixture has to decay
within about a cycle.

### 6.21 At a 20-chord far field the mesh passes checkMesh outright — §6.16's numbers reproduce otherwise exactly

All six decks (three rungs × two arms) meshed on aero-dev. Cell counts reproduce §6.16
**exactly** — 45 682 / 77 240 / 130 032, uniform refinement ratio 1.30 — and
non-orthogonality matches to four significant figures (mid 85.2339 vs the recorded 85.230;
fine 86.3174 vs 86.315), as do the minimum volumes (4.129e-12 vs 4.133e-12 at mid). The two
arms differ only in the fifth significant figure of every metric, so **the paired increment
is not confounded by mesh quality**.

The one difference is aspect ratio: **309.9 here against the recorded 1884.4**, and
`Mesh OK` therefore **passes** on all six where §6.16 recorded it failing. The cause is
`farfield_extent_chords = 20` (the Stage-11/13 plunging-foil precedent, and already four
times more open than HG's own tunnel, whose walls sit 4-5 chords away) rather than the
`CaseSpec` default of 100.

This does **not** overturn §6.16's argument — an absolute M1/M2 gate is still fragile, and
I5 still gates degradation against the recorded baseline — but ADR-039 should say plainly
that at the chosen far field Stage 20's own mesh has no pre-existing failing check to
explain away. **These numbers are still a measurement, not a record**: the I3/I5 pre-flight
must re-run them into `data/vv/` with a four-fold tuple before the ADR cites them.

### 6.22 The fluid and the solid kept DIFFERENT coupling iterates, and the bias differed between arms

`force_io.strictly_increasing_mask` keeps the **first** row at a repeated time;
`ccx_dat._last_occurrence` keeps the **last**. Both files describe the same phenomenon and
under `parallel-implicit` coupling both see it: preCICE re-does a window until it converges,
the OpenFOAM adapter rewinds `runTime`, and the `forces` object re-executes and re-appends.
Only the last row at a window time is the converged iterate — and `flexible_foil.py:252-255`
already states that rule for its own coded object.

So `C_T` and `C_P1` would have come from the accelerator's first guess while `P2` and `P3`
came from the converged solve. **Nothing downstream could see it.** After de-duplication both
arms carry one row per window at identical times, so `assert_common_time_base` passes; D10
compares `P3` against `P2`, both from the last iterate, so the closure check stays consistent;
`eta` merely mixes the two. And because the flexible arm needs more coupling iterations than
the rigid one, **the bias differs between arms** and lands in `dC_T` (D3) and `d_eta` (D4).

Fixed additively: `repeats="first"` stays the default and is byte-for-byte what Stage 10/11/13
did, so no existing record moves. `classify_repeat_cadence` then proves the repeat count is
exactly what the participant's own iterations log accounts for — `duplicates == 0` per-window,
`== sum(iterations) - n_windows` per-iteration, **anything else RAISES**, because an
unexplained repeat is a `timePrecision` collapse and that is silent data loss. Generalise it:
*two readers of one phenomenon must be written against each other, not each against its own
file format.*

### 6.23 An `AlignedPair` could attest to a time base it never compared

Found by the adversarial review, independently by two lenses, with six refuter votes. The
whole point of `AlignedPair` is to be the evidence that two arms are comparable — and it
could not distinguish evidence from its absence.

`align_arms` guarded its bitwise raw-time comparison on **both** `baseline_t` and
`candidate_t` being supplied, but derived `n_samples` from `baseline_t` **alone**. Measured by
the reviewers: `align_arms(a, b, baseline_t=t)` returns an object *bitwise identical* to a
fully checked one while never having compared a single instant; `align_arms(a, b)` records
`n_samples = 2`, a fabricated number that clears its own `ge=2` floor and reads as a
measurement; and `align_arms(a, b, candidate_t=t)` reports 2 for a 9600-sample record.
Reproduced end to end: a one-time-step shift that the two-sided call refuses loudly is
accepted silently by the one-sided call.

Three changes. The arrays are all-or-nothing. `n_samples` is `int | None`, bound to a new
`time_base_checked` by a validator — honest absence over a fabricated number, the ADR-025
precedent. And **the segmentation-anchor clause, which RESUME §7 requires and which was
missing entirely, is now unconditional**: the reviewers' correction is what makes it cheap —
`LimitCycleAnalysis.t_start` is `t_kept[0] + converged_from_cycle * period`, so the
post-discard origin comes back as `t_start - converged_from_cycle * period` from fields both
analyses already carry, with no raw times needed. **Equal `discard_s` does NOT imply equal
origins**: the origin is the first *sample* at or after the discard, so one dropped row moves
it by a time step and every index-`k` pair then compares different physical intervals.

Generalise both: *a field that records what was verified must be unable to claim more than
was verified*, and *an optional argument that silently disables a check is a check that will
eventually not run.*

### 6.24 `tests/stage_20` has never been in CI

`.github/workflows/test.yml:37` runs `pytest -q tests/unit` and nothing else. The mandated
`pytest -q tests/unit tests/stage_20` suite is a local and PR-author discipline; **664 green
is not 664 enforced**. Consequences, both acted on:

- **ADR-039's binding tests go in `tests/unit/`**, beside `tests/unit/test_stage19_gate_block_sync.py`
  — which is where the Stage-19 precedent already put them, and is why the ADR-036 gate block
  IS CI-enforced. A pre-registration whose parity test does not run is not a pre-registration.
- **`config_hash` for the FSI3 spec embeds absolute host paths** (`TutorialPin.manifest_path`,
  `TutorialSource.archive_path` are `Path` fields and serialize as absolute strings), so
  `3f94f394…` is a property of *this checkout*, not a portable fact. ADR-037 must say so where
  it records the move. `AuthoredSource` is path-free and a test pins that it stays so.

The CI job itself was NOT widened in-stage: doing that mid-stage would run fixtures that have
never executed on a GitHub runner. Carried in the ledger.

### 6.25 Three more silent failures closed while both specs were in one place

All three became *possible* to check only because ADR-037 put the fluid and solid specs on one
object; all three were unreachable before.

- **Nothing cross-checked the solid's geometry against the fluid's.** `assert_calculix_deck`
  compares a deck against the spec it was written from — self-consistent by construction — and
  `grep -rn surface_x` outside `calculix.py` and its own test returned nothing. A pair with the
  flexible plate on the fluid and the rigid plate on the solid validated, wrote, meshed,
  coupled, converged, and would have reported a thrust coefficient somewhere between the two
  arms. **Plate thickness is the only thing distinguishing the arms.**
- **`n_through_thickness` could be odd.** `_grid` lays nodes at `eta = linspace(-1, 1, n+1)`,
  which contains `0.0` only for even `n`. At an odd count there is no mid-surface node and
  **preCICE snaps a watch-point to the nearest vertex with no diagnostic**, so D0 became the
  angle of a surface fibre — offset by the plate half-thickness times the local rotation, and
  entirely plausible.
- **Mixed participant uids.** Nothing required every `ParticipantSpec.run_as_uid` to equal
  `spec.run_as_uid`. A root participant creating `precice-run/` its unprivileged peer cannot
  write into hangs both, and the ceiling stop that follows is an ending **gate K2 admits** as a
  budget outcome. Cost: one full 14-day wave before anything complains. The same shape applies
  to a wrong `exchange_directory`, which is why `EXCHANGE_DIRECTORY` is now one constant
  asserted against the launcher's cleanup path.

### 6.26 The resumed adversarial review: fourteen candidates, refuters dead again, verified by hand

The session-5 review resumed from cache; its finder panels for the two named blind spots
COMPLETED, then all 46 remaining agents (every refuter, the synthesis) died on a usage limit
— the second time. The fourteen candidates were verified against the code by hand instead.
Eleven were real and are fixed: `b222c18` (candidates 12/13 — **eta was a ratio over the
whole post-discard record while every sibling mean used the settled window, and the sibling
means themselves were flat sample means over a window that generically ends mid-cycle**;
both landed straight in gated quantities; every gated mean now rides `of(name).mean`, the
settled integer-cycle estimator) and `94c3306` (candidates 1-2, 4-11 — material VALUES never
compared so a 10x-softer plate passed; `NLGEOM=NO` parsed as on; truncated node-set includes
passed; a self-consistent 20x-coarser amplitude table passed; mixed-element decks passed;
stray `*CLOAD`s invisible; only the upper wetted curve checked; `_INC_MARGIN` 10 vs the
coupling's own max-iterations 50; the template's watch-point names were a third hand copy;
and the 'verbatim from upstream' numerics were only ever checked copy-vs-copy — now closed
against the pinned archive's own bytes). Candidate 3 (`PreciceConfigExpectation` cannot
observe the convergence-measure mesh, m2n acceptor/connector, provide/receive-mesh, or
extra watch-points) is ledgered. Candidate 14 (convergence certified on the fundamental
only) became ADR-039's per-signal S5 plus `aero/vv/fsi/preflight.signal_drift_reports`.

### 6.27 calculix-precice.sif ships no pyprecice — I1's dummies cannot run there

Measured: `apptainer exec calculix-precice.sif python3 -c "import precice"` →
`ModuleNotFoundError`. The I1 solverdummies therefore ran (and PASSED) in
`precice-fsi.sif` through the real launcher, and the cross-SIF m2n property is carried by
the same-day two-container smoke at HEAD. Recorded as a deviation in
`data/vv/stage20_i1_solverdummy.json`, not silently absorbed.

### 6.28 ccx's printed RF at a prescribed dof EXCLUDES the applied *CLOAD — D10's residual is real

The F12 question, answered by a differential pair of uncoupled runs: a known dof-2 load on
the 534 non-prescribed interface nodes (run A) versus all 876 including the 342 nose-cap
nodes that are in BOTH `Nsurface` and `Nnose` (run B) prints **identical** `Nnose` RF
totals. So `<RF.v> = <P2>` closes with a residual equal to the applied-force work at the
prescribed overlap — and the nose carries a large share of the fluid force, so **expect D10
to miss on bookkeeping at verdict time**, with `data/vv/stage20_i9_ccx_conventions.json` as
the explanation and the fluid-side nose-share force as the X-family diagnostic beside it.
The band froze before the answer arrived; that ordering is what pre-registration means.
Also measured there: `*AMPLITUDE` reads clean at 120,005 AND 1,200,005 rows (rc=0), so the
table is not the binding constraint at any surviving dt.

### 6.29 THE BUDGET WALL: the pre-registered campaign misses its own ceilings by 1-2 orders of magnitude

The stage's central session-7 result, in four measured steps:

1. **The candidate dt fails Courant immediately.** At `dt = 3.5e-4` the FIRST window
   prints max Co 9.61 (flexible) / 9.62 (rigid) — the steady convective Courant at the
   19 um TE base cells. §6.11's wall-cell arithmetic was right, and the hoped-for
   relative-flux slack did not materialize. The flexible arm then diverged at window 5
   (Co → 239.8, GAMG FPE, rc=136); the rigid arm was killed clean after the bound was
   shown unpassable. `suggest_next_dt(9.61, headroom 0.8)` → **2e-5 s**, and the re-probe
   measured window-1 Co **0.549 on both arms** — the linear scaling held to three digits.
2. **A Courant-passing window is expensive.** The completed 500-window calibrations
   (both arms, all-exited, wave-1 contention shape — I4's own criterion) measured
   **16.08 s/window at 5.25 coupling iterations (flexible)** and **9.12 s/window at
   4.18 (rigid)** — ~3.1 s wall per coupling iteration, with healthy IQN convergence
   (`Convergence 1` throughout, NOT added-mass distress).
3. **The arithmetic is fatal, in the committed rule's own words.** The gated campaign
   needs `(3 + 20) x T = 23.33 s` of physical time = **1.18M windows** at dt 2e-5;
   `size_gated_campaign` on the real record: *"flexible projects 18762387s > 1209600s,
   rigid projects 10640030s > 1209600s - a budget NO-GO is a recorded outcome (ADR-039
   B4), not a band change"* — **217 and 123 days against the 14-day ceiling** (15.5x and
   8.8x; still 7.8x/4.4x at the 10-cycle last resort). The 1.5-period I7 probe itself
   (76,090 windows) projects 120-398 h against its frozen 43,200 s submission ceiling —
   killed, recorded, replaced by the calibrations. And the F4 disk warning is now a
   number: **497 time directories retained for 500 windows** (purgeWrite does not track
   FO-written fields), 343 MB per 500 windows → **~810 GB per arm** at campaign scale.
4. **The committed sizing rule refuses**, by design: no completed post-ramp I7 exists and
   the projection exceeds the ceiling, so `size_gated_campaign` raises, B2 stays
   `<<B2-PENDING-I4>>`, the sentinels stay `None`, and no configuration can claim the
   gated verdict. The pre-flight bought this knowledge for ~3 hours of box time instead
   of a burned 14-day wave.

Cost decomposition (hypotheses with their evidence, for ADR-040): the ~3.8 s/iteration
plausibly splits between serial pimpleFoam on 77k cells (~1-1.5 s/step measured on
comparable decks), per-iteration adapter checkpointing of full fields, the ccx increment
(~0.03 s, measured in the spike), preCICE exchange, and `forces1`'s registered-field
writes at every step (`writeControl timeStep`) hitting NFS ~5x per window. None of these
fractions is separately measured yet — measuring them is ADR-040's first job.

### 6.30 76125 x 2e-5 = 1.5225000000000002 — window counts must be chosen through the round-trip check

`2e-5` is not dyadic, so `n * dt` accumulates binary error and the CalculiX
field-width validator (§6.17) rightly refused the first re-probe spec. 76090 x 2e-5
= 1.5218 survives `%.13e` exactly. The sizing rule already bumps its window count to the
first round-tripping value; hand-chosen probe counts must do the same
(`float(format(n*dt, '.13e')) == n*dt`).

### 6.31 SESSION 8 — the cost split, measured: two of the three named levers are dead

§6.29 left four candidate cost terms "hypothesis-ranked, not measured". Measured now, from
the I4 runs' own surviving logs at **zero box cost** (`data/vv/stage20_i10_cost_split.json`,
produced by the committed `--collect-cost` mode):

- **99.42 %** of the flexible arm's wall clock is fluid-participant CPU (7988.69 s of
  8035 s). All I/O, preCICE exchange and waiting on CalculiX totals **46.3 s over 500
  windows**. `forces1` **write scheduling is refuted** by that bound — and it was also
  mis-specified: `writeControl writeTime` would stop the `force.dat` rows the readout is
  built on, not just the field dumps.
- **Fluid subcycling is refuted** by the same bound plus the 6.0 % per-step overhead share
  (only 1 in K recurs). Total fluid step-solves are `T_phys/dt_f × iterations` — invariant
  in K, because each coupling iteration re-solves every substep. State the ~6.6 % ceiling,
  not 0.58 %: a reviewer who computes the intercept term will otherwise think it was missed.
- **90.8 %** of fluid CPU is the pressure solve: 961 GAMG iterations per fluid step over 8
  pressure solves, at 2.87 ms each, a per-iteration convergence factor of **0.89**.
- The disk attribution in §6c item 4 is **wrong**. Growth is the CalculiX `.frd` at **78 %**,
  which nothing in this repo reads, not `forces1`'s field writes at 7.6 %. The lever is a
  `FREQUENCY` card on the solid deck.
- **Both bounds are rate-dependent and the record says so.** A 0.58 % residual at
  16 s/window is not one at 1.5 s/window; the ccx `.frd` write becomes a real wall-clock
  term the moment the fluid is parallel.

### 6.32 SESSION 8 — one token is worth 2.22x, and parallelism is the weaker lever

`data/vv/stage20_n2_screening.json` (RANKS ONLY — fluid-only, static mesh, 20 steps; its
control runs at 1.013 s/step against the campaign's 3.041, so the ratios are indicative).

- `smoother GaussSeidel` → **`DICGaussSeidel`** is **2.22x** and drops GAMG iterations per
  step from 302 to 51. GAMG's coarse-grid correction was not working under a plain
  Gauss-Seidel smoother at aspect ratio ~310.
- **PCG+DIC is 1.07x.** `_foam_common.fvsolution`'s own docstring recommends it for extreme
  aspect ratios; here it takes 1114 iterations where tuned GAMG takes 51. Do not re-derive.
- Agglomeration tuning **hurt** relative to fixing the smoother alone (1.78x vs 2.22x).
- Tier 2: one outer corrector → 3.37x; plus a looser `p` tolerance → **3.73x** serial.
- **Strong scaling turns over**: 2.18x at 6 ranks (36 % efficiency), *slower* at 8.
- **Combined 8.04x** ⇒ ~2.00 s/window uncontended, against 1.037 needed for 20 settled
  cycles in 14 days and 1.834 for 10. **The 14-day ceiling is out of reach at any
  settled-cycle count**; the deferred ceiling decision is live and will be taken on the
  coupled, contended confirmation.

### 6.33 SESSION 8 — three traps found by building it

1. **`mpirun` must sit INSIDE the `setpriv` uid drop.** Measured: as root OpenMPI refuses
   outright. So `build_apptainer_exec(mpi_n=…)` is the WRONG seam for the coupled launcher —
   at that call site `command` is the compound `cd … && … && pimpleFoam` (or the whole
   `setpriv … bash -lc '…'` wrapper), so it would emit `mpirun -n 6 cd fluid-openfoam`,
   run the solver serial and **exit 0**, or run `mkdir` as root six times. The seam is
   `build_participant_command`.
2. **`nOuterCorrectors 1` is a deck change, not a knob.** OpenFOAM then tags every inner
   iteration final and demands `cellDisplacementFinal`; a deck carrying only
   `cellDisplacement` dies with `FOAM FATAL IO ERROR` on the first time step.
3. **ADR-039's sentinels can never be filled.**
   `test_adr039_b2_marker_state.py::test_the_gated_sentinels_track_the_marker` asserts
   `GATED_TIME_WINDOW_S is None` *while* `<<B2-PENDING-I4>>` stands — and it must stand
   forever, since that campaign was measured infeasible and never ran. So **ADR-040 needs
   its own sentinels and its own `--submit-040`**, and `--submit` keeps refusing forever.
   Also: `_merge_base_guard` resolves commits with `git log --diff-filter=A`, so the
   ADR-040 calibration must go in a NEW file or the guard compares against session 7's
   add-commit and passes on the wrong ordering.

### 6.34 SESSION 9 — both named leads are refuted, and §6.31's attribution was wrong

Session 8's N2 record explains the campaign's 961 GAMG iterations/step against the static
screen's 302 by "the deforming mesh makes the pressure system about three times harder".
That was a hypothesis, and it is **false**. Measured on a committed harness
(`scripts/stage20_numerics_screen.py`, `data/vv/stage20_n4_deforming_screen.json`) that
reproduces N2's `s0_control` to four significant figures before measuring anything new:

| variant | s/step | `p` it/**solve** |
|---|---|---|
| `d0` static, ADR-039 stack | 1.089 | 35.6 |
| `d1` **moving**, ADR-039 stack | 1.249 | **40.3** |
| `d2` `d1` + `cacheAgglomeration no` | 1.334 | 41.3 |
| `d3` moving, candidate stack | 0.294 | 5.6 |
| `d4` `d3` + `cacheAgglomeration no` | 0.348 | 5.7 |
| `d5` `d1` + fully-Dirichlet farfield `p` | 1.223 | 39.0 |

1. **N4 (`cacheAgglomeration`) is refuted.** On a mesh that *does* move it removes no
   iterations at all and costs 6.8 % wall time (18.4 % on the candidate stack). The knob was
   untestable on N2's static screen; it is now tested and dead.
2. **N5 (the near-pure-Neumann pressure system) is refuted.** `0/p`'s farfield really is
   `freestreamPressure` on one 20-chord patch with `zeroGradient` walls. Pinning the WHOLE
   farfield — the strongest possible form of the fix, deliberately over-constrained — is
   worth 3 %, inside scatter. **No campaign boundary condition changes.**
3. **The refutation is a fortiori.** Under the (1-cos) ramp the campaign's foil had moved
   **2.6e-7 m by its 0.01 s end time — 0.006 of ONE wall cell**. The screen has no ramp and
   moved it **167x further**, and still reproduced almost none of the cost. Both sides of
   §6.31's 3x in fact ran on an effectively static mesh.
4. **What the cost actually is: startup-transient difficulty, sustained forever.** The
   screen's own first five steps cost 78.2 it/solve from uniform fields and decay to 40.3 by
   step five, because a marching solve warms up from the previous step's converged field.
   The campaign's first five step-solves sit at **91.2 — the screen's STARTUP number, not
   its settled one — and never decay** (113.0 over all 2627 solves). Under implicit coupling
   every iteration restores the window-start checkpoint, so the pressure solve is
   permanently cold-started. This fits all four measured signatures: present from the first
   solve, flat across position in the window (987 on iteration 1 vs 977 on iteration 3),
   flat in time, and untouched by both refuted knobs. The lever it implies is the
   per-iteration initial guess, which lives in the coupling scheme **ADR-039 C1 freezes** —
   so it is REPORTED, not acted on.
5. **The budget projection is conservative, not optimistic.** The candidate stack's
   advantage is LARGER cold-started (5.29x) than warm (4.25x), and its moving-mesh ratio
   (4.25x vs the moving control, 3.70x vs the static one) brackets N2's 3.73x. So
   ~2.00 s/window stands, the 14-day ceiling is still out of reach at any settled-cycle
   count, and the ceiling conversation is unchanged. It remains a PROJECTION and still may
   not size — only a coupled, contended confirmation past the ramp may.

N2's committed record is left untouched; the correction lives in the new record with its
evidence, per §9's rule that a measurement record is never edited in place.

### 6.36 SESSION 9 — the rank count: 6 was measured in the wrong conditions

ADR-040 must pre-register ONE rank count with no free knob. The standing operator decision
(6 fluid ranks per arm, 14 of 16 cores) rests on §6.32's ladder, which was **uncontended** and
on a **static** mesh — both wrong conditions, since wave 1 runs both arms on one box and the
campaign mesh moves. Re-measured in the wave-1 shape (two arms concurrently, moving mesh,
binding on the slower arm because the wave is not done until both are):

| config | cores incl. ccx | binding s/step | `p` it/solve |
|---|---|---|---|
| 1+1 | 4 of 16 | 0.2867 | 5.6 |
| 2+2 | 6 of 16 | 0.2844 | 6.1 |
| **4+4** | **10 of 16** | **0.1655** | 9.1 |
| 6+6 | 14 of 16 | 0.1860 | 12.1 |

**4 ranks per arm**, about 10 % faster than 6 while leaving four more cores free. The
uncontended moving-mesh ladder agrees and is sharper: pressure iterations per solve rise
monotonically 5.6 / 9.2 / 11.4 / 18.4 / 36.1 across 1/2/4/6/8 ranks, and an iteration count is
a far more robust witness than a wall clock on a shared box. Both contenders carry repeats and
the record reports the MEDIAN — a rank count chosen off its luckiest run is chosen off noise.

Caught by the new tests, not hypothetically: the rank-ladder pass wrote to the same filename as
the canonical serial run, so `--run d3 --ranks 6` silently overwrote d3's serial baseline and
the record compared the candidate stack against itself at six ranks. Non-canonical runs are now
keyed, and `--record` REFUSES to assemble a variant table from anything but the serial
configuration.

### 6.35 SESSION 9 — `--collect` would have failed after wave 1's weeks of wall clock

Verified by hand on **both** surviving I4 arms, from bytes already on disk:

- `classify_repeat_cadence` **RAISES**. `force.dat` carries `sum(iterations)` rows over
  `n_windows + 1` distinct times, so repeats are `sum(iter) - n_windows - 1`, one short of
  what the classifier requires. Its error message blames `timePrecision`, which is wrong.
- `_assert_one_schedule` **RAISES**. The fluid-side records carry 501 instants starting at
  `t = 0`; the CalculiX `.dat` carries 500 starting at `t = dt`.

The structure is exact and reproducible: per-time row counts **equal** the per-window
coupling-iteration counts for every window `k >= 1` (499/500 exact on both arms),
`cnt[0] = it[0] - 1`, plus one trailing row at `max_time`. So the fluid function objects
stamp the window **START** and CalculiX stamps the window **END** — a one-window phase
offset between the fluid force and the solid reaction, sitting directly under **D10**
(`|P3-P2|/P2`) and under P2/P3. This is the §6.22 defect class again.

`--collect` -> `read_arm` has **never been run on a real coupled run** — the I4 pair was
collected through `--collect-probe` and `--collect-cost` only. It must be fixed
structurally (never with a `+1`) and proved against these bytes BEFORE wave 1, or a 20-day
campaign ends in a raise.

### 6.37 SESSION 10 — the parallel seam works, and the L-smoke earned its two minutes

`mpi_ranks` on `ParticipantSpec`, and `mpirun -n N <command> -parallel` appended as the
LAST element of `parts` INSIDE `build_participant_command`. Session 8 measured why the
obvious seam is wrong in two different ways; both are now also pinned as negatives in
`tests/unit/test_precice_launcher.py`, beside the serial byte-pin, which is untouched.

`decompose()` lands beside `mesh()` and differs from it deliberately. `blockMesh` runs as
container root because `constant/polyMesh` is only read afterwards; `decomposePar` WRITES
`processor*/` and `pimpleFoam` writes into them every step, so it routes through
`build_participant_command` with the participant's own uid. Its `model_copy` CLEARS
`mpi_ranks` — `decomposePar` is serial, and the seam would otherwise wrap it in `mpirun`.

**The L-smoke passed all four clauses on the real coupled deck**
(`data/vv/stage20_l6_smoke.json`, run `hg2007_flexible_foil-20260812-214956`, 20 windows at
4 ranks): the staged supervisor carries the mpirun element exactly once, after the `cd` and
inside the `setpriv` drop, with nothing before the drop mentioning mpirun; four `processor*`
directories for four requested ranks; `all-exited` with both participants rc=0 and zero
non-converged windows; and **L2 re-measured on the coupled deck** — `force.dat` lands in the
case root, so the readout needs no change under decomposition. Session 9's L2 was a
fluid-only screen.

The cost block in that record **may not size anything** and says so: 322 step-solves over 20
windows is 16.1 iterations/window, the coupling's start-up transient rather than the
campaign's 5.25, and the wall clock includes the coded FO's first compilation. What it does
show as a sanity check is **0.795 s per step-solve against the ADR-039 baseline's 3.041**,
which brackets the screen's 4.36x.

### 6.38 SESSION 10 — the fluid stamps the window START, and the proof is iterate convergence

Session 9 established the one-window offset from row counts. Session 10 measured it to a
sharper standard, because the fix depends on which reading is right and the row counts alone
admit more than one.

Re-measured on both surviving I4 arms:

- `force.dat` carries `sum(iterations)` rows over `n_windows + 1` distinct times;
- the row count at distinct time `k·dt` **equals** the coupling's iteration count for window
  `k+1`, for every `k >= 1` — **499/500 exact on both arms** — with `count[0] = it[0] - 1`
  and one trailing row at `max_time`;
- **the decisive check**: grouping the rows that way yields a monotonically converging
  `|dF|` sequence in **100 %** of windows (500/500 flexible, 465/465 rigid), and the
  alternative grouping — converged iterate at the window END — in **0 %**.

So the rows at one stamp ARE one window's fixed-point iteration, and `repeats="last"` at
`(w-1)·dt` correctly returns window `w`'s converged force. §6.22's fix stands. What does not
is the pairing: the fluid's converged force for window `w` is stamped `(w-1)·dt` and the
solid's reaction for the SAME window is stamped `w·dt`.

Window 1's one-row deficit is the coded FO not emitting on its very first execution — a
missing row INSIDE window 1, not a row belonging to another window, so it shifts nothing.

**Two things that look like they should discriminate, and do not.** The summed reaction
against the interface force cannot: §6.28's `*CLOAD` exclusion makes the printed RF a
residual, not the total, and the correlation is 0.13 on the flexible arm. Neither can
`power / F_y` against the analytic plunge velocity: the FO reads the WALL velocity, which
deep in the impulsive start is dominated by the plate's own deformation rate and runs
1e-2 m/s against the ramped plunge's 1e-6. Both were tried; only the iterate-convergence
structure settles it.

The fix is `aero/adapters/precice/schedule.py`: every series DECLARES its convention, the
1-based window index is derived from that declaration, and the join is on an integer. A
`+1` at one call site would have been the §6.22 defect wearing a fix's clothes. The
analysis time base is now the window-END instant — the moment each window advanced the
solution to — so **P1 and P3 are evaluated at the same instant**, where before they differed
by one window. That was a signed bias in the very quantity D9 exists to expose.

### 6.39 SESSION 10 — two latent faults in the collector, both of which would have fired

Neither was hypothetical and neither was in §7's list.

1. **`_collect_probe` crashed on every run inside the ramp.**
   `f"{record['i7']['max_courant_post_ramp']:.4f}"` raises `TypeError` when the run did not
   reach the post-ramp window, and both fields are `None` in exactly that case. **Both
   committed I4 bundles are in that state.** The bundle is written before the print, which
   is why the records exist and the mode reported a crash. Q1 would have hit it again.
2. **The time-directory count read essentially zero under decomposition.** `find -maxdepth 3`
   found **1** directory on the L-smoke's parallel case against **69** at `-maxdepth 4`:
   OpenFOAM writes `processor*/<time>`, one level deeper than the serial layout. That count
   is the input to the F4 disk projection, which is the thing standing between a 20-day wave
   and a full NFS four days in.

Related, and recorded rather than fixed: under `mpirun`, OpenFOAM's `ExecutionTime` is
**rank 0's CPU**, not the aggregate, so I10's 99.42 % bound does not transfer to a parallel
run. The N3 rate is read from `ClockTime`, which is wall clock at any rank count and prints
at integer-second resolution — ample over a run of hours.

### 6.40 SESSION 10 — Q1 ACCEPTS, and the clause that had room to fail is the increment

500 coupled windows at the I4 shape, both arms concurrently at 4+4 ranks on the
`adr040-candidate` stack, against the surviving ADR-039-numerics I4 runs. Bands and the
rejection outcome were fixed in ADR-040 Q1 before either probe ran; the baseline side cost
nothing (`data/vv/stage20_q1_equivalence.json`).

| clause | flexible | rigid | band |
|---|---|---|---|
| Q1a span-mean streamwise force | 0.046 % | 0.0021 % | 2 % |
| Q1b trace vs baseline peak-to-peak | 2.25 % | 2.31 % | 5 % |
| Q1c increment of the span-means | 3.53 % | — | 5 % |

**The third row is why it is a separate clause.** The two arms reproduce the baseline to
0.05 % and 0.002 %, which on its own reads as "the stacks are identical" — and their
DIFFERENCE still moves 3.5 %, because the increment is a small number between two large
ones and inherits both their errors. A common-mode shift must not read as an increment
failure, and an anti-symmetric one must not read as a pass. The record test pins that
relationship as an inequality rather than as today's numbers.

Q2's limits ride in the record: the I4 shape sits inside the ramp, and the comparison is of
the configuration AS DELIVERED — numerics and the 4-way decomposition together — so a
rejection would not have localized.

### 6.41 SESSION 10 — the rate came in worse than B0 was sized on, and B0 was raised BEFORE N3

Q1's most consequential by-product is not the equivalence verdict. It is this: **the
per-step-solve cost is FLAT under contention.** The flexible arm ran 0.753 s/step-solve
while sharing the box and 0.711 s over the whole run; the rigid arm 0.482 against 0.485. So
the flexible arm's early slowness — 5.16 s/window over its first 500 windows — is entirely
its **iteration count** (11.06 per window over the first fifty, settling to 4.90), and
contention is nearly free at 4+4 on 16 cores.

That yields a binding N3 projection of **3.69 s/window** (0.753 × 4.90), against the
2.8 s/window pessimistic figure B0's 72 h was sized on:

| target | windows | projected |
|---|---|---|
| clear the ramp | 50 726 | 52.0 h |
| ramp + 1 quarter-cycle (the W3 minimum) | 63 407 | 65.0 h |
| ramp + 1 half-stroke (the chosen span) | 76 090 | **78.0 h** |

72 h would have cut the run **5875 windows short** of the phase-complete sample the span
was chosen for. **B0 raised to 96 h (345 600 s), before N3 ran**, with the measurement that
forced it written into the clause. Admissible for two reasons the clause states: B0 governs
a PROBE and not a gate, and it is raised before the probe rather than after seeing its
result. Recorded rather than quietly adjusted — that is the whole difference between a
pre-registration and a number.

**One risk is knowingly carried.** 3.69 s/window is measured on RAMP-phase windows, where
the plunge is near zero and the mesh barely moves; post-ramp, at full amplitude, iterations
may rise. If they rise enough the run reaches B0 without a whole post-ramp quarter-cycle,
which ADR-040 W3 makes a FAILURE — correctly, and expensively. `--project-n3` exists so
that verdict arrives at hour 52, when the ramp clears, instead of at hour 96. It reads the
running run's own append-only logs, is safe on a live run, and takes no action: stopping
early is an operator decision and W3 already says what happens otherwise.

### 6.42 SESSION 11 — N3 SIZES, and the gap to B0's basis is iterations, not cost

Polled twice while N3 ran, 2026-08-13 00:31 and 01:08 UTC (1 h 32 m and 2 h 10 m in).
`--project-n3` was verified strictly read-only before use: `_project_n3` calls no
`_write_bundle`, no `_executor` and no `_run_long`; its only I/O is two `read_text` calls on
the append-only `Fluid.log`.

**Both arms project SIZES.** The binding arm is flexible, as expected.

| | window | `--project-n3` (whole-run) | marginal (2nd half) | iters/window | s/step-solve |
|---|---|---|---|---|---|
| flexible | 1703 / 76090 | 4.331 s/win | **3.871 s/win** | 5.158 | **0.750** |
| rigid | 3211 / 76090 | 2.381 s/win | 2.279 s/win | 4.194 | 0.543 |

**Read the marginal rate, not the headline one.** `--project-n3`'s ramp-phase figure
differences `ClockTime` from the run's FIRST step, so it carries the coded FO's first
compilation and the decomposition read for the whole projection. That startup amortizes:
the same arm read 4.534 s/window at window 1221 and 4.331 at window 1703, and its marginal
rate over the second half of what has run is 3.871. Over 76 090 windows the startup share
is negligible, so the marginal rate is the one the ceiling conversation is about.

**The decomposition against §6.41's basis (0.753 s/step-solve × 4.90 iterations = 3.69
s/window) is the useful part:**

- per-step-solve cost **0.750 vs 0.753 s — flat to 0.4 %**. §6.41's finding that the cost
  is flat under contention holds exactly, now on a run 3× longer than the one that measured it;
- iterations per window **5.158 vs 4.90 — up 5.3 %**, and that is the entire gap;
- product **3.871 vs 3.69 — up 4.9 %**.

Projected from the second poll: the **W3 minimum** (ramp + one whole post-ramp
quarter-cycle, 63 406 windows) lands at **68.4 h**, and the **chosen span** (ramp + one
half-stroke, 76 090 windows) at **82.0 h against B0's 96 h — 14.0 h of margin**. Rigid
finishes its full span at 48.3 h and is not binding.

**One caveat carried unchanged from §6.41**: every number above is measured on RAMP-phase
windows. Post-ramp, at full amplitude, iterations may rise, and the margin above is what
absorbs it. Re-poll as the ramp clears at ~window 50726 — that is when the W3 verdict
becomes real rather than projected.

Coupling convergence, measured while checking the rate: N3 flexible has **4 non-converged
windows in 1702** and all four are inside the first 280; N3 rigid has 1 in 3212. Q1's
flexible arm, by contrast, had **12 in 500**, nine of them clustered in windows 301-400.
So N3 is better behaved than the probe it was sized from, and the clustering in Q1 was a
local event rather than a trend. Recorded because gate K1 refuses non-converged windows
inside the analysis window, and the campaign's analysis window is its settled tail.

### 6.43 SESSION 11 — `--collect` refuses at the DISCARD guard, not the S-rule

RESUME §7 expected `--collect` on a finished Q1 arm to clear the window join and then
refuse on the S-rule for want of settled cycles. **It refuses earlier, on a different
clause, and the join never executes.** Not a defect — the correction is the finding.

`read_arm` calls `solver.load()` on its FIRST line (`hg2007_readout.py:227`; its docstring
says the ordering is the point, because obtaining `solve` is what enforces K2, C4 and K1).
`_load_authored` (`solver.py:841`) then runs `analyse_limit_cycle` on the **watch-point**
time base with `discard_s = spec.analysis_discard_s = 3.0434782608695654 s`. A Q1 arm spans
`[0, 0.01] s`, so `keep = t >= discard_s` is all-False and it dies at
`limit_cycle.py:209-215`:

```
NO-GO (LimitCycleError: discarding t < 3.04348 s leaves no samples
(record spans [0, 0.01] s) — the run has not passed the start-up transient)
```

Identical on both arms, exit code 1, bundle written. The window join, `gated_means`,
P1/P2/P3 and D10 all live in `read_arm` **downstream of `load()`** and are never reached.

**What the run did prove**, on real 4-rank decomposed bytes for the first time:
`_submission` schema acceptance, `_reattach`'s status/rc/digest round trip,
`solver.reattach`, `coupled_status`, gate **K2** (`stopped_by='all-exited'`, both rc 0),
gate **C4** on both watch-points (501 rows each, headers verified against the rendered
config), and the nose/tip instant-equality check.

**The number that matters for wave 1**: a collect cannot clear `load()` until the record
carries `analysis_discard_s + analysis_min_cycles × period` = 3.0435 + 10 × 1.0145 =
**13.19 s = 659 420 windows** at dt 2e-5. No probe will ever have that. The gated campaign
will, because `size_gated_campaign_040` builds `max_time` from the discard plus **20**
settled cycles and 20 ≥ 10 — but that agreement was implicit, and `--size-040` now asserts
it (`test_the_sized_campaign_is_long_enough_for_its_own_readout`).

aero-dev exposure for the whole exercise: two read-only SSH calls per arm, both inside
`_reattach` — `run_long.sh status` and `cat ~/.aero-jobs/<session>/rc`. `reattach`,
`coupled_status`, `watchpoint` and `coupling_report` take no executor and read host-side NFS.

### 6.44 SESSION 11 — a lost submission is recoverable, and the manifest is the witness

The Q1 submissions were written to `/tmp` at submit time and are gone; NFS carries none.
They are exactly reconstructible, and — this is the part worth keeping — the reconstruction
is **provable** rather than assumed, because `<run>/tutorial/aero-manifest.json` carries
`authored.spec_sha256`, written by the materializer at prepare time.

Knobs, both arms: `rung="mid"`, `time_window_size=2e-05`, `max_time=0.01`,
`wall_clock_ceiling_s=259200`, `numerics_label="adr040-candidate"`, `mpi_ranks=4`.
Rebuilt at HEAD, `spec_config_digest` reproduces the manifests exactly — `ed91a14a5e8e…`
flexible, `d6c516794950…` rigid — so `_reattach`'s digest check stayed a real check rather
than comparing a number against itself. The reconstructed records carry an explicit
`reconstruction` key naming the manifest they were verified against, and **no `provenance`
block**: the Q1 run's four-tuple is not recoverable, and RESUME §8 forbids writing a
provenance-bearing field that was not computed. They live in the session scratchpad, not
the repo.

**The same mechanism now guards N3.** `tests/unit/test_n3_live_submission_digest_is_pinned.py`
(commit `2a90489`, landed alone and first) rebuilds both in-flight specs from their live
`spec_knobs` and asserts `bfc60a49…` / `ed1ba571…`. Any edit to `CoupledCaseSpec`,
`ParticipantSpec`, `FlexibleFoilSpec`, `CalculiXSolidSpec` or `AuthoredSource` — including
one that adds a field nothing reads — would make N3 uncollectable, and the symptom would
otherwise appear only at the collect, three days and 76 090 windows after the mistake.
**Delete that file once N3 has been collected.** The digests were re-verified straight off
NFS after every commit this session; both still match.

### 6.45 SESSION 11 — `read_arm` has now executed, and D10 has a precision FLOOR

`tests/unit/_hg2007_case_tree.py` builds a complete settled case — the real materializer
writes the deck, and the outputs a run would leave are written analytically around it:
per-iteration `force.dat` stamped at the window START (with window 1 one row short and one
trailing row at `max_time`, the structure §6.38 measured), a ccx `.dat` stamped at the
window END, both watch-points, both iterations logs, the coded object's power lines,
`coupled-status.json`. Time constants are SCALED — 0.05 s period, 0.1 s discard — so eight
settled cycles fit in 500 windows.

`read_arm` completes: 500/500 windows through the join, cadence `per-iteration`, 7 settled
cycles, `force_t[0] == dt` (the analysis base is the window-END instant, §6.38's fix
observed at the far end of the path rather than at the join).

**It is a fixture and the file says so** — this proves the code against bytes this repo
wrote, not against a solver. What makes it worth more than "it runs" is that the series are
analytic and **P3 == P2 by construction**, so the D10 closure is a number the test asserts
rather than merely one the code produced. A 5 % error injected into the reaction record
alone moves D10 to 0.0500, past the test's bound and past ADR-039's 2 % band, which is what
says the gate would catch the same defect on real bytes.

**The new measurement: D10 closes to 1.3e-8, not to 1e-16, and the reason is real.**
CalculiX prints reaction forces to SEVEN significant digits
(`ccx_dat._PRINT_SIGNIFICANT_DIGITS`), so P3 is rebuilt from a 7-digit number while P2 rides
in the fluid log at full precision. That is a **floor of order 1e-7 on how tightly D10 can
ever close on real bytes**. ADR-039's D10 band is 2 %, five orders of magnitude above the
floor, so the identity is comfortably measurable — but the floor is now on the record
rather than waiting to surprise someone who tightens the band.

Separately, `TestAgainstTheSurvivingI4Bytes` is now parametrized over **four** runs rather
than two: the two serial I4 arms and the two **4-rank decomposed** Q1 arms, in one id space
so a claim added later is re-derived on both. Every claim holds on both decompositions,
including the iterate-convergence structure. Wave 1 is decomposed, and until now every
claim about the join rested on serial bytes.

### 6.46 SESSION 11 — N3's FLEXIBLE ARM DIED: CalculiX heap corruption at window 1703

**This supersedes §6.42's projection.** The projection was correct while it lasted; the run
did not last.

At **2026-08-13 01:04 UTC**, 2 h 03 m in and at **window 1703 of 76 090 (2.2 %)**, the
flexible arm's CalculiX participant aborted:

```
corrupted double-linked list
[aero-dev:753676] *** Process received signal ***
[aero-dev:753676] Signal: Aborted (6)
```

`ccx_preCICE` exited **rc=134** (SIGABRT), the fluid then exited rc=1, and the supervisor
wrote `stopped_by=participant-died`. That is glibc detecting **heap corruption inside
CalculiX** — not a numerical divergence, and not the box running out of memory: aero-dev
had 27 GB of 32 free at the time. It fired between Newton iterations 6 and 7 of one
coupling iteration, immediately after a `no convergence` line, which is where ccx is
re-factorising.

**Gate K2 refuses this run as evidence, and correctly.** ADR-040 W6 (citing ADR-039 N3)
pre-authorises exactly **ONE** resubmission — both arms, new run ids, both bundles shipped
— and states that a second death is a **NO-GO on infrastructure**. That one attempt is now
the only one left, which is why it is worth spending some thought before spending it.

> **[CORRECTED — see §6.48.]** The K2 refusal stands; the W6 reading does not. W6 and
> ADR-039 N3 both scope themselves to *"a wave-1 solve"*, and N3 is a PROBE under budget
> B0. No resubmission was spent and none is at stake here; wave 1's one-resubmission
> protection is untouched. The paragraph above is kept as written because this section is
> a record of what session 11 believed while deciding — §6.48 is the correction of record.

**Four facts that bear on the decision:**

1. **It is not a window-count wall.** The rigid arm was at window **3353 and healthy** when
   the flexible arm died at 1703, and is still running. Whatever this is, it is specific to
   the arm that exercises CalculiX hardest.
2. **The flexible solid works ~6× harder inside ccx.** `no convergence` lines — ccx's own
   internal Newton retries — run at **27.7 per window** on the flexible arm against **4.3**
   on the rigid one. The flexible plate is the one actually deforming; the rigid plate
   barely does. That is the intended physics, and it is also the load under which ccx broke.
3. **The rigid arm running on alone can no longer size B2 either.** N3's whole value is a
   CONTENTION-measured rate. With its partner dead, the remainder of the rigid run is
   uncontended, and `size_gated_campaign_040` refuses an uncontended confirmation by name
   ("was measured alone"). Letting it finish yields a diagnostic, not a sizing input.
4. **A disk projection nobody had yet, and it is large.** CalculiX's `.frd` is being written
   at **~537 KB per window** on the flexible arm (914 MB at 1703 windows) and ~549 KB on the
   rigid one. That is **~41 GB per arm over N3's full span**, and — the number that matters
   — **~1.27 TB for both arms over the gated campaign's 1.17 M windows**. `/mnt/aero-nfs`
   has 24 TB free, so it fits; but it is a per-wave cost nothing in ADR-040 B2's disk
   projection anticipated, and the F4 ladder should see it before wave 1 rather than four
   days in. If the `.frd` write frequency is reducible in the solid deck, that is a real
   lever — and it touches frozen deck bytes, so it is an ADR question, not an edit.

**Nothing was done about it.** Killing the surviving rigid arm and re-submitting are both
operator decisions: one is destructive, and the other spends the single resubmission ADR-040
W6 allows *(corrected in §6.48: it does not — a re-run is an ordinary B0 probe)*. Both are
queued for the operator with the evidence above.

### 6.47 SESSION 11 — the ccx abort, diagnosed as far as it can be without spending the retry

Operator decisions taken on the evidence in §6.46: **let the rigid arm run** (it cannot size
B2, but it answers the question that decides how the retry is spent) and **diagnose before
spending ADR-040 W6's single resubmission**. Both are recorded here so neither is
re-litigated. **DO NOT KILL `fsi-hg2007_rigid_foil-20260812-230109`.**

> **[RESOLVED + CORRECTED — see §6.48.]** The rigid arm COMPLETED all 76 090 windows on
> 2026-08-14 and the discriminator below has an answer: candidate 1 is REFUTED. And the
> "single resubmission" framing was a misreading of W6's scope — the constraint protects
> wave 1, not this probe.

Two candidates, measured, ranked, with the thing that would separate them.

**Candidate 1 — repeated spooles factorisation. The leading one.** CalculiX re-factorises
on every Newton iteration, and the flexible arm does far more of them:

| | spooles lines | per window | factorisations before the abort |
|---|---|---|---|
| flexible (died @1703) | 113 080 | 66.4 | **~56 500** |
| rigid (alive @3353) | 58 782 | 17.5 | ~29 400 and counting |

The abort fired **immediately after a factorisation and a `no convergence` line** — the
re-factorisation path itself. Spooles allocates and frees its factor structures on every
call, so ~56 500 cycles is the largest source of allocation churn in the process, and it is
also the dimension along which the dead arm and the surviving one differ most (3.8×
per window). This is a hypothesis with good circumstantial support, not a proof.

**Candidate 2 — the `.frd` write path.** CalculiX writes it at **537 KB/window**, confirmed
to three digits across three separate runs (268 689 148 B at 500 windows in the I10 record;
914 338 912 B at 1703 windows here). The deck's `*NODE FILE U` and `*EL FILE S, E` carry
**no `FREQUENCY` card**, so ccx dumps displacements, stresses and strains on every
increment. Weaker as a corruption candidate — a 914 MB sequential write is not obviously
heap-corrupting — but it matters regardless, for a reason that is not about the abort at
all (below).

**What discriminates them, and it is already running.** If the rigid arm reaches 76 090
windows it will have completed **~667 000 factorisations**, an order of magnitude more than
the flexible arm managed before dying at ~56 500. Surviving that rules out raw factorisation
count as the trigger and points instead at something specific to the flexible arm's much
larger deformations — ill-conditioning, or an element approaching inversion — which is a
different fix. Dying short of it makes candidate 1 the answer and makes the campaign
infeasible on this ccx build without a change. Either way the next session starts with a
real result rather than a coin flip. **That is what the rigid arm is now for.**

> **[RESOLVED — §6.48.]** It survived, and by more than the pre-registered margin: the
> completed run shows **1 156 014** spooles lines (15.2/window), not the ~667 000 the
> per-window estimate projected — **10.2×** the flexible arm's pre-abort total. Raw
> factorisation count is ruled out.

**The `.frd` is a B2 problem in its own right, independent of the abort.** Session 8 already
found it — `data/vv/stage20_i10_cost_split.json` attributes ~78 % of disk growth to a file
**no code in this repo reads**, and
`test_stage20_i10_cost_record.py:test_the_disk_growth_is_the_frd_that_nothing_reads` names
the `FREQUENCY` card as the lever. It was recorded and not acted on, because at 500 windows
it was 268 MB. At the gated campaign's 1.17 M windows it is **~1.27 TB across both arms**.
`/mnt/aero-nfs` has 24 TB free so it fits, but nothing in ADR-040 B2's disk projection
anticipated it, and the gated readout demonstrably does not need it: the campaign's numbers
come from `precice-Solid-watchpoint-*.log`, the `.dat` written by `*NODE PRINT`, `force.dat`
and `Fluid.log` — never from a `.frd`.

**Adding a `FREQUENCY` card is an ADR question, not an edit**, and deliberately left as one.
It changes frozen deck bytes, moves the spec's `config_hash`, and would therefore fail
`test_n3_live_submission_digest_is_pinned.py` — which is the guard doing exactly its job,
because the rigid arm is still running against the current bytes. If the retry is spent on a
mitigated configuration, the ADR must record the byte change, the digest move (the ADR-037
precedent), and that Q1's equivalence verdict was measured on the unmitigated stack.

### 6.48 AUDIT (2026-08-15) — the rigid arm COMPLETED, the discriminator resolved, W6 read wrong

Written during the pre-move audit, from the completed run's own bytes and the ADR texts.
Three findings; the first two are measurements, the third is a correction to §6.46/§6.47
and the session-12 path, which were written before the run finished and around a
misreading.

**1. The rigid N3 arm COMPLETED.** `fsi-hg2007_rigid_foil-20260812-230109` ended
2026-08-14 05:57 UTC, `stopped_by=all-exited`, both participants rc=0, **all 76 090
windows**, wall clock **111 400 s (30.9 h)** — much faster than §6.42's 48.3 h projection
precisely because it ran uncontended after its partner died. Post-ramp rate **1.296
s/window over 25 365 windows** (two whole quarter-cycles) against a ramp-phase 1.547 —
post-ramp came in CHEAPER than the ramp for this arm, so the risk carried since §6.41
(post-ramp iterations rising) did not materialise on the rigid side. The rate still may
not size B2: uncontended, and single-arm (§6.46 item 3 stands). `.frd` final size
**40 857 949 088 B = 40.9 GB**, confirming the ~41 GB/arm projection to three digits; the
~1.27 TB campaign figure stands.

**2. §6.47's discriminator has an answer: candidate 1 is REFUTED.** The completed run
carries **1 156 014 spooles lines over 76 090 windows (15.2/window)** — not the ~667 000
the per-window estimate projected, because the estimate was built on the mid-run 17.5/window
sample. Against the flexible arm's **113 080 over 1703 windows (66.4/window)**: the rigid
arm executed **10.2× more factorisations than the flexible arm managed before aborting**,
with zero corruption. Raw factorisation count / allocation churn is ruled out as the
trigger. By §6.47's own pre-registered reading, that "points instead at something specific
to the flexible arm's much larger deformations — ill-conditioning, or an element
approaching inversion — which is a different fix." The supporting asymmetry stands:
`no convergence` retries 27.7/window flexible against **4.2/window rigid (320 566 total)**.
Candidate 2 (the `.frd` write path) is further weakened — 40.9 GB written cleanly. The
flexible arm's 1703 windows of `Solid.log` remain unmined; that mining needs no box.

**3. W6 does not govern N3, and the "single resubmission" framing was wrong.** §6.46
(twice), §6.47, this file's §7 (twice) and RESUME §6g/§7 treated the N3 death as spending
"the single resubmission ADR-040 W6 allows". The clauses say otherwise, by their own text:

> `W6 if a wave-1 solve ends participant-died, ADR-039 N3 applies unchanged: one`
> `   resubmission, both arms, new run ids, both bundles shipped, ...`

> `N3 if a wave-1 solve ends participant-died ... the wave may be resubmitted ONCE ...`
> `   This is a declared deviation from ADR-036's no-restart rule: a 14-day exposure is`
> `   not a 48-hour one, and a died run carries no gated numbers to retry.`

Both scope themselves to **"a wave-1 solve" / "the wave"**, and ADR-039 N3's stated
rationale is a 14-day exposure. The N3 confirmation is a PROBE — submitted through
`--probe`, `label="probe"`, `gated=False` — and probes are governed by budget **B0**,
which exists precisely because a probe cannot be ceilinged by the campaign clauses. B0
arithmetic at the time of writing: consumed 122 531 s of 604 800 s total (L6 270 + Q1
2 580 + 901 + N3 7 380 + 111 400) = **20.3 %, leaving 134 h**; the worst single
submission used 30.9 h of the 96 h per-submission ceiling. **An N3 re-run is an ordinary
B0 probe. It spends nothing that W6 protects, and wave 1's one-resubmission protection is
fully intact and untouched.**

The likely mechanical origin of the misreading is the naming collision ADR-040 itself
flagged when it W-prefixed its contingencies: "ADR-039 N3" (a contingency about wave-1
resubmission) and "N3" (the coupled confirmation run) are different objects with one name.
The dilemma §6.47 queued for the operator — spend the one attempt vs diagnose first —
dissolves: **both**, in either order, and the only genuinely scarce resources are B0's
remaining 134 h and calendar time. What remains true from §6.46: K2 refuses the dead run
as evidence, a re-run must be both-arms to be contended, and if the abort RECURS the
campaign is infeasible on this ccx build without a mitigation ADR — that, not any budget
clause, is the real reason to mine the flexible arm's logs before re-running.

### 6.49 SESSION 12 (2026-08-29, post-move) — the abort has a 150-window PRECURSOR, and N3 was NOT resubmitted

First session after the house move. Step-0 re-verification: rack whole (post-boot-verify
2026-08-29), NFS mounted rw/hard with 24 T free, aero-dev idle (zero `pimpleFoam`/
`ccx_preCICE` processes by exact-name pgrep), tree clean at `b9fd72c`, **962 tests green
+ mypy clean on `aero/`** — the post-move environment is whole. Nothing ran on aero-dev
this session beyond those two read-only ssh checks.

**How the mining was done.** The SESSION-12 path's first item, executed as an 11-agent
workflow: six independent read-only miners over the dead arm's structured records
(`.cvg`/`.sta`/`Solid.log`/watchpoints/`Fluid.log`/preCICE logs, with the completed rigid
run and the Q1 flexible run as controls), a synthesis applying a PRE-STATED precursor test
(baseline envelope over windows 101-1600, terminal statistic over 1601-1702; anything
occurring only inside increment 1703 inadmissible as cause), then two adversarial
verifiers — one re-derived every number from scratch off the tables, one attacked the
mechanism — **both upheld, zero unresolved refutations**. The tables AND the exact parsers
that produced them are preserved at `/mnt/aero-nfs/runs/stage20-n3-attempt1-mining/`
(sibling directory; the run dirs themselves untouched).

**The finding: a period-2, odd-window exponential instability inside CalculiX, starting
~150 windows before the abort.**

1. **Odd-window absolute residuals grow exponentially from window ~1557**: 34.8 N →
   1665.4 N (~48×) by w1701, doubling every ~26 windows (~0.52 ms), while **even windows
   monotonically DECREASE** (18.585 → 18.464 N, argmax pinned at node 2091). The commanded
   plunge amplitude grew only 1.19× over the same span — a symmetric load ramp cannot
   produce a parity split with one branch falling. This is a coupled-solve instability,
   not load tracking.
2. **ccx Newton effort escalates in lockstep, odd windows only**: 39 windows with final
   ITER ≥ 8, ALL odd, an unbroken run 1625..1701 escalating 8→9→10→11→12→14→13,13 — then
   the fatal window 1703 aborts at iteration 7. Zero `U` rows before 1703 (the sole `U`
   is the death), zero CONT.EL anywhere in all three runs.
3. **The argmax node marches into the death cluster**: strict cluster
   {2059,2060,2062,2152,2160} share of per-window residual argmax is **0 % over windows
   101-1600 → 6 % over 1601-1700 → 67 % over 1701-1703** (2100→2069→2070→2052→2060, with
   period-2 alternation 2060(odd)/2091(even) from ~w1691). The BROAD TE-tip dominance is
   generic geometry — the healthy rigid control has 97.06 % TE-tip argmax at the same
   x = 0.090 (node 2155 winning 100 % of its last 1000 windows); the strict-cluster
   *intensification* is the discriminator.
4. **§6.46's "345.9 unprecedented spike" reading is REFUTED** — it was iteration 6 of the
   death window, not the peak: 13 SURVIVED windows exceeded 345.9 N; the prior global max
   was **1665.4 N, survived, at w1701**; the death window's true max is 2027.0 N = only
   1.22× that; no pre-1703 window ever jumped >1.174× the running max. And the `.cvg`'s
   headline "1.5e8" figures are ccx's RESID.FORCE **percentage**, normalized by a
   near-zero early-ramp average force — absolute residuals never exceeded ~2 kN.
5. **The interface is blind to all of it.** preCICE coupling health is clean and
   IMPROVING into the death (last 300 windows are among the run's healthiest: mean 4.85
   iterations, negative slope); the fluid series are clean (death-step Courant **0.1139**
   — the 0.549 quoted around §6.46 was the t=0 startup value, a misattribution corrected
   here); the interface 2·dt lift sawtooth was DECAYING (2.7e-3 → 8.3e-4 N RMS). The
   precursor is visible ONLY in the ccx-side records (`.cvg`/`.sta`/`Solid.log`) and the
   elastic-tip watchpoint — ~80 windows (~1.6 ms) of warning that nothing was watching.
   A solid-side absolute-residual watchdog at ~10× the baseline ceiling (44.3 N) would
   have fired at ~w1650, 53 windows before death.
6. **The rigid control quantifies "healthy"**: over all 76 090 windows, per-window max
   absolute residual p99 = 2.02 N, whole-run max = **4.37 N** — the dead arm's terminal
   values are 380× that. One cap-50 window (2196), recovered within 2 windows; at the
   flexible death time the two arms' fluid series are statistically indistinguishable
   (Courant 0.115 vs 0.114). The discriminator is solid-interior.
7. **Determinism is DIVERGENT, which undercuts §6.48's re-run rationale.** Byte-identical
   decks (F vs Q1, only the step duration differs; plunge.amp identical row-for-row)
   split at the FIRST parallel GAMG solve at t = 2e-5 (15 vs 16 iterations), 80.8 % of
   the first 500 INCs differ in `.cvg` row counts, TE Force1 deviates 3.6 % at window 1
   and O(100 %) by t = 0.0022 s. An unmitigated re-run reproducing — or not reproducing —
   the abort at window 1703 is therefore NOT a sharp measurement; "reproducibility of the
   abort is itself the discriminating measurement" no longer holds.
8. **Proximate killer vs precursor state.** The SIGABRT landed after iteration 7's
   residual had RECOVERED to 3.86 N, and the fluid had already completed window 1703
   cleanly (it died of the broken socket). The heap corruption is CalculiX-2.20-internal
   and timing-sensitive — the Q1 control was SICKER in coupling health (12 cap-50 windows
   vs this run's 4, all four startup: 57/138/216/247) and died of nothing. The 150-window
   period-2 divergence is the mitigation target; the memory bug is the final blow it
   exposes the process to.

**Verdict, per the pre-registered rule: MITIGATION-WARRANTED** — precursors in six series
from FOUR independent source files (rule requires two), each passing both sub-tests with
margin, plus a mechanism-consistent account of the rule's first enumerated kind (strict
death-cluster argmax intensification with absolute-magnitude growth). The four startup
cap-50/Convergence=0 windows technically hit an instant qualifier but are recorded as
not load-bearing (the rigid control survived an identical event; Q1 survived twelve).
The settled non-candidates stay refuted: factorisation churn (§6.48), cumulative retry
count (rigid total 320 566 > flexible 47 251), the `.frd` path.

**Consequence: N3 was NOT resubmitted.** The SESSION-12 path's own stop rule ("if
evidence demands a deck change, STOP — that is a mitigation ADR") fired. Nothing was
submitted, B0 stands untouched at 134 h remaining, and the digest-pin test stays (nothing
in flight, but N3 remains uncollected). **The mitigation decision is queued for the
operator**, with the option space and what each moves:

- **(a) Deck-byte mitigations** (ccx `*CONTROLS` tightening, damping, output cards):
  move the spec `config_hash` — the ADR must record the byte diff, the digest move
  (ADR-037 precedent), and that Q1's equivalence verdict was measured on the UNMITIGATED
  stack. `test_n3_live_submission_digest_is_pinned.py` fails by design and is re-pinned
  in the same commit.
- **(b) Coupling-scheme/config mitigations** (preCICE acceleration parameters,
  serial-implicit ordering): C1 is FROZEN under ADR-040 U2 — same ADR weight as (a).
- **(c) A ccx build change** (the heap bug lives inside CalculiX 2.20): moves the
  container SHA — P1/P3 provenance, a new pin, an ADR.
- **(d) Hash-exempt observability only** (solid-side residual watchdog reading
  `Solid.log`, core-dump ulimit, glibc malloc tunables in the ENVIRONMENT): moves no
  spec bytes, but observability alone removes nothing — it converts the next death from
  a mystery into a measurement.

**The open physics question the ADR conversation must face:** the instability set in at
~w1557 of the RAMP, at 0.27 % of the final commanded amplitude, near no kinematic
extremum. If odd-window growth is a genuine property of this coupled configuration, the
gated campaign's 1.17 M windows at FULL amplitude cannot run on the unmitigated stack
regardless of the memory bug — which makes (d)-alone a fragile bet and (a)/(b) the
branches that address the disease rather than the coroner's report.

### 6.50 SESSION 13 (2026-09-05) — ADR-041 drafted, and THREE of §6.49's sentences corrected

Step-0 re-verification: NFS mounted rw/hard (24 T free), mining dir intact, aero-dev IDLE
(exact-name `pgrep -x` for `pimpleFoam`/`ccx_preCICE`/`ccx_2.20`/`mpirun` all empty; zero
tmux sessions), tree clean at `ab5a11f`, **962 tests green + 2 skips, mypy clean on
`aero/`**. Nothing was submitted this session up to this point; B0 stands at 134 h.

**ADR-041 was drafted and adversarially verified BEFORE going to the operator** (three
rounds: 4 skeptics on the first draft, 2 on the revision, 2 on the rewrite). The first
two rounds found 3 blockers and 14 majors between them; the ADR was rewritten twice. Four
findings are worth carrying forward regardless of what the operator decides about the ADR:

1. **§6.49's "a 443 N absolute watchdog would have fired at ~w1650" is REFUTED by its own
   table.** The first window whose max absolute residual exceeds 443 N is **w1683**
   (474.19 N) — 20 windows before death, not 53. ~w1650 is where an idealized
   doubling-every-26-windows fit crosses 443 N, not where the measured series does.
2. **§6.49's "even windows monotonically DECREASE (18.585 → 18.464 N)" is wrong in
   direction.** Over w1558-1700 the even-window maxima RISE monotonically from 17.490 N
   (w1558) to 18.586 N (w1662), then sag 0.7 % to 18.461 N (w1698) — a +6.3 % swing, not a
   decrease. The parity split itself is untouched and is what matters: **47.8x on the odd
   branch against 6.3 % on the even one**.
3. **An ABSOLUTE newton threshold cannot be the campaign's watchdog at all**, which is why
   ADR-041 does not use one. The healthy per-100-window residual ceiling tracks the
   commanded load (0.65 → 24.49 N over w1-1500, excluding the w1 startup transient of
   1.883 N at ~1e-7 % of amplitude), and full campaign amplitude is another ~16x beyond
   w1500. Any threshold quiet during the ramp is guaranteed to fire on healthy
   full-amplitude operation. What separates sick from healthy is **parity**, measured on
   three datasets: worst 20-window odd/even ratio (both parities ≥ 1.0 N) is **1.81**
   (flexible healthy w101-1540), **1.53** (Q1 control), and **2.45** on the RIGID arm's
   COMPLETE 76 090-window run — the only healthy coupled data at full amplitude — against
   **3.21 → 5.48 → 10.14 → 21.08 → 76.63** over the dying arm's last five chunks.
4. **preCICE forbids the D-B rung as "rename one element".** Its documentation states that
   *"for serial coupling, you can only configure primary data from coupling data which is
   exchanged from the `second` to the `first` participant"* — and the pinned template
   exchanges `Force` Fluid→Solid (first→second) while accelerating BOTH data. A
   serial-implicit variant therefore cannot keep the IQN-ILS primary-data set
   `{Displacement, Force}`; it becomes `{Displacement}`. That is a SECOND frozen C1
   element, forced rather than chosen, and it changes the quasi-Newton acceleration
   itself. Any future session considering serial-implicit must budget for that.

Also verified for the record: `--record-q1` writes `args.out or
data/vv/stage20_q1_equivalence.json` (driver line 1537) — **the default overwrites the
accepted unmitigated Q1 record**, so any re-run must pass an explicit `--out`;
`_reattach` rebuilds via `hg2007_case_spec(**spec_knobs)`, so a builder-default flip would
retro-break every existing submission (both uncollected N3 attempt-1 records included) —
ADR-041 pins a frozen `LEGACY_COUPLING_SCHEME` in the reattach path instead; and the
window-count round trip re-checked: 8000 and 4000 survive `.13e`, 6000 does not.

**The ADR text is with the operator. Nothing else has run.** The draft is on disk,
deliberately UNCOMMITTED, at
`docs/adrs/ADR-041-flexible-arm-ccx-instability-mitigation-ladder.md` — its own header
says acceptance is recorded in the commit that lands the file (the ADR-040 `d5bf381`
pattern), so it lands accepted or not at all. If a session opens and that file is absent,
it was never accepted and the ladder was never authorized: re-derive it from this section
plus §6.49 rather than assuming any part of it ran. Its verdict vocabulary, detector
bounds and the 35 h ladder cap are the parts a re-derivation must not soften.

### 6.51 SESSION 13 — ADR-041 ACCEPTED, the detector shipped, and D-A IS RUNNING

**The operator accepted ADR-041 on 2026-09-05** (`2bbfdd4`; the ADR is
`docs/adrs/ADR-041-flexible-arm-ccx-instability-mitigation-ladder.md`, and the acceptance
IS that commit). Three commits implement it, in the mandated order:

- `b962c7d` — **the divergence detector** (`aero/adapters/precice/logs.py`:
  `read_solid_residuals`, `evaluate_divergence`), wired into `--status` and
  `--project-n3`, so V4 holds: every future poll of every coupled run carries it.
  Verified read-only against the runs themselves — dead arm PRECURSOR at **window 1660**
  (43 windows pre-death), Q1 clean (1.53/1.70), rigid complete run **INCONCLUSIVE** at
  4.8 % activation rather than a false "clean" — and the parser reproduces
  `minerB_parse.awk` on all 1703 windows of the dead arm at that table's own precision.
- `b6da94f` — **observability** (`ObservabilityOptions` on the launch plan, injected into
  the participant compound inside the uid drop). Core dumps on for every coupled run this
  driver submits; `MALLOC_CHECK_=3` armed ONLY on a ladder rung via the new
  `--adr041-rung`; both recorded in the submission JSON. The library default is off, so no
  byte-pinned participant command in the suite moved.
- Suite **979 green + 2 skips**, mypy clean, pushed.

**aero-dev pre-flight for the rung, recorded because V5 asks for it:**
`kernel.core_pattern` is `core` — cores land as a file in the participant's own workdir,
NOT piped to a collector — and the core rlimit is soft 0 / hard unlimited, so
`ulimit -c unlimited` is raisable inside the drop. 31 GB free, box idle before submit.

**D-A IS RUNNING — the box is NOT free.** Submitted 2026-09-05 22:02 UTC:

```
run_id   hg2007_flexible_foil-20260905-220206
session  fsi-hg2007_flexible_foil-20260905-220206
submission JSON  /mnt/aero-nfs/runs/hg2007_flexible_foil-20260905-220206/ladder-DA-submission.json
poll     bash scripts/run_long.sh status root@aero-dev fsi-hg2007_flexible_foil-20260905-220206
         python scripts/stage20_hg2007_flexible_foil.py --status <submission JSON>   # prints the detector
```

8000 windows (0.16 s), flexible arm only, **uncontended**, mid rung, adr040-candidate,
4 ranks, 12 h ceiling; `adr=ADR-041`, `adr041_rung=D-A`, `note="diagnostic probe under
ADR-041; sizes nothing"`, `observability={core_dumps: true, malloc_check: true}`,
`gated=False`, 4 processor dirs confirmed before submit. Expected ~3-9 h.

**Nothing else may run on aero-dev until it finishes** — V3 registers rung probes as
uncontended, and a contended rung is not the measurement the ADR pre-registered.

**Measured rate, 10 minutes in: 3.25 s/window marginal (the first-window average of
6.1 s/window is startup-loaded), so 8000 windows projects to ~7.2 h against the 12 h
ceiling — ~1.7x headroom, and inside V3's "~3-9 h per rung". ETA ~05:15 UTC 2026-09-06.**
Max Courant is being read from the fluid log on each poll; nothing has fired.

**Evaluate it with one command when it lands** — `--adr041-evaluate` (`5ebbe8f`) does the
whole of V1/V2 and writes the evidence beside the run:

```
python scripts/stage20_hg2007_flexible_foil.py --adr041-evaluate \
  /mnt/aero-nfs/runs/hg2007_flexible_foil-20260905-220206/ladder-DA-submission.json
```

It refuses while the probe is still running (V1 spends the rung's one verdict when it is
taken), derives the verdict rather than accepting one, and writes
`adr041-D-A-solid-residuals.tsv` (minerB's five columns, so the two diff cleanly) plus
`adr041-D-A-verdict.json` (verdict, why, detector report, AND the bounds that produced it,
so the decision re-derives without the driver).

Two more commits land the rest of what the ADR requires regardless of which rung wins:
`5ebbe8f` (the V1 verdict derivation + the evidence writer) and `4622e26` (**V7's
template-of-record fence**, in the spec factory as well as at the submission boundary,
because `--probe` submits with `gated_intent=False` and a boundary-only check would let a
probe mint `gated=True` on a template the campaign never adopted). Suite **990 green**.

The verdict, per V1's closed vocabulary: ELIMINATED / RECURRENCE-DETECTED /
DIED-UNDIAGNOSED / INCONCLUSIVE / UNRESOLVED. **A clean D-A adopts the unmitigated stack and goes straight to the V6 Q1
re-run; anything else steps the ladder to D-B**, whose serial template must be rendered
and PARSED before its probe (D-B is BLOCKED if preCICE forces any change beyond the two
the header already declares).

### 6.52 SESSION 13 — D-A's VERDICT: RECURRENCE-DETECTED. The instability is reproducible.

**The ladder's first rung failed, and it failed informatively.**
`hg2007_flexible_foil-20260905-220206` died at **window 1487 of 8000** after 5645 s
ClockTime (~1.57 h) with the SAME signature as attempt 1 — `corrupted double-linked list`,
SIGABRT, `ccx_preCICE` rc=1 through mpirun. Verdict under ADR-041 V1, derived not typed:
**RECURRENCE-DETECTED** (a fired prong wins even when the probe then dies). Evidence at
`/mnt/aero-nfs/runs/hg2007_flexible_foil-20260905-220206/adr041-D-A-{verdict.json,solid-residuals.tsv}`.

**Three things this establishes, none of which was known before:**

1. **The instability is REPRODUCIBLE.** Attempt 1 died at w1703; this independent run,
   which shares no timing with it (determinism is divergent from the first parallel GAMG
   solve), died at **w1487** carrying the same period-2 parity signature. §6.49's finding
   was one observation; it is now two, on runs that agree on the mechanism and disagree on
   the window. **The unmitigated stack is not a candidate for the 1.17 M-window campaign**
   — that question is now settled by measurement rather than by inference from a single
   death.
2. **The detector works PROSPECTIVELY.** It fired at **window 1460**, 27 windows before
   the death, on a run it had never seen, with the bounds fixed in an accepted ADR before
   the probe was submitted. Worst parity ratio 46.02 at chunk w1461-1480, against a
   healthy worst of 2.45 anywhere in the corpus. (In attempt 1's post-hoc replay the same
   rule fired 43 windows early; 27 is the prospective number and it is the honest one.)
3. **The core-dump half of V5's observability FAILED, and the reason matters.** The kernel
   created `solid-calculix/core.31023` and wrote **0 bytes** into it, owner root although
   the participant runs as uid 1000. That is the classic consequence of a privilege
   change: `setpriv` clears the process's dumpable flag, so the kernel suppresses the
   dump. `ulimit -c unlimited` was necessary and is not sufficient. Fixing it needs
   `prctl(PR_SET_DUMPABLE, 1)` after the drop (or `fs.suid_dumpable=2` on the host, which
   is a host change and therefore an operator decision). **MALLOC_CHECK_=3 did reach both
   participants but did not move the detection point** — the abort message is glibc's own
   `unlink` consistency check, identical to attempt 1's.

**Budget:** D-A cost 1.57 h of ADR-041 V3's 35 h ladder cap. **33.4 h remain in the cap**;
B0 is otherwise untouched.

**Next, per V1's fixed order: the ladder advances to D-B (serial-implicit).** D-A is spent
— RECURRENCE-DETECTED is terminal for its rung and is not re-probable. Before any D-B
probe: the serial template must be rendered AND PARSED (preCICE is the authority, not the
ADR), and **if the parser forces any change beyond the two the ADR's header already
declares — the scheme element and the IQN-ILS primary-data set dropping to
`{Displacement}` — D-B is BLOCKED pending its own operator-accepted ADR.**

### 6.53 SESSION 13 — D-B's PARSE GATE PASSED (and proved the forced change); D-B IS RUNNING

ADR-041 put a gate in front of D-B: preCICE, not the ADR, decides what serial coupling
forces, and **any change beyond the two the header declares blocks the rung**. The gate was
run against preCICE's own validator inside the SIF, and it passed:

- `precice-config-validate serial.xml Fluid 4` and `... Solid 1` — **"No major issues
  detected"**, exit 0, identical to the parallel control.
- The counterfactual — the serial scheme with `Force` KEPT in the IQN-ILS data — is
  **rejected by name**: *"For serial implicit coupling schemes, only data exchanged from
  the second to the first participant can be used for acceleration ... you configured data
  'Force' ... exchanged from 'Fluid' to 'Solid'. Please remove this acceleration data tag
  or switch to a parallel implicit coupling scheme."* So the drop to `{Displacement}` is
  **FORCED, measured rather than inferred from the documentation**.
- **Nothing further is forced.** Both 5e-3 relative convergence measures survive
  (the open question the docs could not settle), max-iterations 50, QR2 at 1e-2,
  initial-relaxation 0.5, max-used-iterations 100, time-windows-reused 15 and the
  participant order are all byte-identical to the parallel template. D-B needs no second
  ADR.

`0736e8a` lands the template and the knob. Two properties protect history and are tested:
the scheme is a **keyword** selecting a committed template through `AuthoredSource.template`
— never a pydantic field, which would move every digest — so the default path's digest is
unchanged and **both live N3 pins still pass**, while a serial spec hashes differently by
design (`a3189144…` against the parallel `72365ada…`); and `_reattach` supplies
`LEGACY_COUPLING_SCHEME` explicitly for records written before the key, so flipping the
builder's default at adoption can never retro-break a record describing a run on disk.

**D-B IS RUNNING.** Submitted 2026-09-07 12:08 UTC:

```
run_id   hg2007_flexible_foil-20260907-120835
session  fsi-hg2007_flexible_foil-20260907-120835
submission  /mnt/aero-nfs/runs/hg2007_flexible_foil-20260907-120835/ladder-DB-submission.json
poll     python scripts/stage20_hg2007_flexible_foil.py --status <submission JSON>
verdict  python scripts/stage20_hg2007_flexible_foil.py --adr041-evaluate <submission JSON>
```

Same span and shape as D-A — 8000 windows, flexible only, uncontended, 4 ranks,
adr040-candidate, 12 h ceiling, both observability flags — with `--coupling
serial-implicit`. The materialized `precice-config.xml` was checked in place: it really is
`<coupling-scheme:serial-implicit>`. **Nothing else runs on aero-dev until it lands.**

If D-B is ELIMINATED it is the adopted mitigation and the V6 Q1 re-run follows on it
(and the adoption commit then moves the template-of-record, re-pins the digests to the N3
resubmission, and adds the serial cadence fixtures). If it is RECURRENCE-DETECTED the
ladder goes to D-C form 1 (ccx `*CONTROLS` deck bytes) — which, unlike D-B, permanently
un-reattaches both attempt-1 records, as §6.52 and the ADR both record.

Ladder budget after D-A: **1.57 h of 35 h spent**; D-B projects ~7 h at D-A's rate.

### 6.54 SESSION 13 — D-B's FIRST SUBMIT WAS ABORTED ON MY CEILING, AND SERIAL COSTS 1.76x

**Recorded plainly because it is the kind of thing a later reader must be able to audit.**
The first D-B submit (`hg2007_flexible_foil-20260907-120835`, 12:08 UTC) was **killed by me
at window ~111, 17 minutes in**, and it was NOT killed for anything the solve did:

- serial-implicit settled at **5.71 s/window against D-A's 3.25 — a 1.76x cost** — so
  8000 windows projected **12.7 h against the 12 h ceiling I had submitted it with**. Left
  alone it would have been stopped by its own ceiling at roughly window 7570 and scored
  **DIED-UNDIAGNOSED**, which under ADR-041 V1 is terminal: the rung would have been spent
  on a budget artefact of my own making and the ladder would have stepped to D-C, which
  permanently un-reattaches both attempt-1 records.
- **No detector information existed when the decision was taken.** The verdict was
  NO-DATA — fewer than one complete chunk past w101, and the parity signature does not
  appear until ~w1400 in either prior death. This is a correction to a submission
  parameter, not a re-roll after seeing a result, and V1's one-probe rule is about the
  latter. The aborted record is renamed `ladder-DB-ABORTED-ceiling-too-small.json` so it
  can never be read as the rung's probe.
- Cost: ~0.28 h of the 35 h ladder cap.

**Resubmitted with a 24 h ceiling** as `hg2007_flexible_foil-20260907-122616` (12:26 UTC),
everything else identical; submission JSON copied to
`/mnt/aero-nfs/runs/hg2007_flexible_foil-20260907-122616/ladder-DB-submission.json`.
Ladder budget: **1.85 h of 35 h spent**, D-B projects ~12.7 h.

**The 1.76x is itself one of the two numbers D-B was sent to measure, and it has campaign
consequences the operator should see BEFORE any adoption:** ADR-040's N3 projects ~82 h on
the parallel stack, so a serial N3 projects **~144 h against B0's 96 h per-submission
ceiling** — N3 could not complete in one submission on an adopted serial stack. ADR-041
anticipated exactly this ("if the measured cost makes N3 or the campaign unaffordable that
is a budget conversation under ADR-040's B family, taken in the open"), and it is a B3
ceiling question, not something this ladder decides. **The number is early and uncontended;
the settled figure comes with D-B's verdict, and only then is the conversation worth
having.**

### 6.55 SESSION 13 — D-B DIED AT WINDOW 88. Two facts that change the picture.

**Verdict: DIED-UNDIAGNOSED** (recorded at
`/mnt/aero-nfs/runs/hg2007_flexible_foil-20260907-122616/adr041-D-B-verdict.json`), which
under V1 is terminal for the rung. The probe died at **window 88 of 8000**, before the
detector's grid even starts (w101), so V2 could say nothing — which is precisely the state
the vocabulary was written to name rather than argue about. It cost ~0.14 h; the ladder
stands at **1.99 h of the 35 h cap**.

**Fact 1 — the heap corruption fires WITHOUT the parity precursor.** Three deaths now, all
`corrupted double-linked list` inside ccx 2.20: attempt 1 (parallel, contended) w1703, D-A
(parallel, uncontended) w1487, D-B (serial, uncontended) **w88**. In the first two the
precursor was running for ~150 windows beforehand; at w88 no precursor could have
developed — the signature does not appear until ~w1400 in either. §6.49 framed the memory
bug as "the final blow [the divergence] exposes the process to". **That framing does not
survive D-B: the crash is a first-class failure mode of this ccx build, not only the
end-state of the divergence.** (The aborted first D-B submit reached w111 healthy before I
killed it, so the death window varies by more than 20x across identical configurations —
consistent with a timing-sensitive memory bug rather than a deterministic threshold.)

**Fact 2 — serial-implicit is a materially WORSE coupling for this case, on two axes.**
Beyond the 1.76x cost (§6.54), the solid-side residuals are two to three orders of
magnitude larger from the start. Per-20-window maxima over the same early span,
investigation only (the V2 grid starts at w101, and these numbers are NOT a verdict):

| windows | D-A parallel odd / even | D-B serial odd / even |
|---|---|---|
| 41-60 | 0.215 / 0.198 N | 496.9 / 316.8 N |
| 61-80 | 0.419 / 0.362 N | 148.1 / 170.2 N |
| 81-88(100) | 0.622 / 0.508 N | 212.3 / 230.6 N |

That is the forced acceleration change biting: preCICE permits only `{Displacement}` as
IQN-ILS primary data under serial coupling, and on a high-added-mass case losing Force
from the quasi-Newton set leaves the solid far less well conditioned. The parity RATIO is
unremarkable in those windows (1.09-1.57), so serial may well suppress the parity split —
but at a residual level that is not obviously a stack anyone would want to run 1.17 M
windows on, and the run never reached the span where the question could be answered.

**Consequence for the ladder.** The remaining rungs are D-C form 1 (ccx `*CONTROLS`
damping) and D-C form 2 (CalculiX 2.21/2.22 bump), in that pre-registered order, and
ADR-041 requires the operator to be consulted before D-C begins. **The evidence now points
at form 2 rather than form 1**: form 1 targets the divergence, which Fact 1 shows is no
longer the only killer, and form 1 additionally un-reattaches both attempt-1 records
permanently; form 2 targets the crash, which has now ended 3 of 3 runs across two coupling
schemes. Re-ordering them after data exists is exactly what ADR-041 says needs its own
operator-accepted ADR — that decision is with the operator and nothing runs until it is
taken.

### 6.56 SESSION 13 — D-C form 2 AS WRITTEN IS NOT EXECUTABLE, and the better rung is one pin away

ADR-042 X1 promoted "the CalculiX 2.21/2.22 container bump" to the next rung. Investigating
how to build it (read-only, no box time) turned up two things that change what that rung
should be.

**1. There is no adapter for CalculiX 2.21 or 2.22.** `precice/calculix-adapter`'s newest
tag is **v2.20.2**, its master README still reads *"This adapter is based on the source code
of CalculiX v2.20"*, and its own `docs/calculix-support.md` describes porting as a MANUAL
source merge into the solver's main loop: copy `nonlingeo.c` from the new CalculiX, re-apply
the adapter's changes to the time-stepping/communication/checkpointing calls, replace
`ccx_2.<version>.c`, update `CalculiX.h`. That is substantial hand-porting of coupled-solver
C — the kind of work whose most likely by-product is a NEW memory bug, in a rung whose whole
purpose is to remove one. **Form 2 as literally written is not executable at acceptable
risk.**

**2. Our adapter pin is 2.5 years stale, and the gap contains memory fixes.** The container
pins `CALCULIX_ADAPTER_REF=v2.20.1` (2024-03-20). **v2.20.2** (2026-08-05) is 90 commits
later and its changelog fixes, in the adapter C that sits between CalculiX and preCICE:

- **uninitialized counters** — `numNodes`, `nodeSetID`, `numElements`, `faceSetID` were
  never zeroed in `PreciceInterface_Create` ([#165]); a count read before it is set is a
  direct route to an out-of-bounds write, which is what glibc reports as
  `corrupted double-linked list`;
- **"memory access issues during adapter initialization"** — `SimulationData` was being
  initialized too late ([#154]);
- two memory leaks ([#166]).

**A near-miss worth recording so a later reader does not re-find it as a smoking gun.**
Commit *"Remove an invalid free on nodeIDs"* (#173) looks exactly like our bug — it deletes
a `free()` on a pointer INTO CalculiX's own `sim->ialset` array. It is **not in our build**:
that `free` was introduced after v2.20.1 and removed before v2.20.2. Checked, not assumed.

**Recommendation, queued for the operator:** execute form 2 as an **adapter bump
v2.20.1 → v2.20.2 on CalculiX 2.20**, not a CalculiX version bump. It is the same KIND of
change ADR-041 declared for form 2 — a container rebuild that moves the SIF digest, the
ADR-038 roster row and P1/P3 provenance — with a SMALLER consequence, because CalculiX
itself does not move and I9's deck conventions are therefore not re-opened. Nothing has
been built; the substitution changes what ADR-042 X1 names and is the operator's to accept.

**Not proven, and the record should not pretend otherwise:** none of those fixes is
confirmed to be our crash. The case for the rung is that it is cheap, that it is the only
executable form-2-shaped change, and that the fixes are in the right component and of the
right class.

### 6.57 SESSION 13 — the solid container is REBUILT on adapter v2.20.2, and D-C2 IS RUNNING

ADR-042 X1a accepted (`b7bb36c` carries the amendment and the rebuild). The chain, all
verified rather than assumed:

- **Built** on the usual split-host path (buildah on the Proxmox host, apptainer + signing
  on aero-build). The baked adapter commit is
  `f362a16d54a31985712f4c4302128f6923bd1d00`, which **is the v2.20.2 tag exactly**.
- **Rostered**: `calculix-precice.sif` `4ca47da2…` → **`ac0805d6…`**, with the predecessor
  left legible in the SHA256SUMS header because three dead runs name it. The deployed SIF
  on aero-dev hashes to the new digest, and the run record's ADR-038 container list shows
  it, so the provenance is the run's own rather than this note's.
- **Smoked**: `stage20_calculix_smoke.py` (the pinned upstream perpendicular-flap, two
  containers, non-gated) — `stopped_by=all-exited`, both participants rc=0 in 31 s. The
  new adapter's plumbing works before a rung was spent on it.
- CalculiX is UNCHANGED at 2.20, so I9's deck conventions are not re-opened and ADR-041's
  header item 3 stands unused.

**D-C2 IS RUNNING.** Submitted 2026-09-07 15:53 UTC:

```
run_id   hg2007_flexible_foil-20260907-155350
session  fsi-hg2007_flexible_foil-20260907-155350
submission  /mnt/aero-nfs/runs/hg2007_flexible_foil-20260907-155350/ladder-DC2-submission.json
poll     python scripts/stage20_hg2007_flexible_foil.py --status <submission JSON>
verdict  python scripts/stage20_hg2007_flexible_foil.py --adr041-evaluate <submission JSON>
```

8000 windows, flexible only, uncontended, 4 ranks, adr040-candidate, **parallel-implicit**
(D-B's serial is not adopted and not carried), both observability flags, and a **24 h
ceiling** — set from D-A's 3.25 s/window (~7.2 h projected) with the margin D-B's first
submit taught us to leave. **Nothing else runs on aero-dev until it lands.**

Ladder budget: **1.99 h of 35 h** spent before this rung; D-C2 projects ~7.2 h.

**What each outcome means.** ELIMINATED — the adapter bump is the adopted mitigation, and
V6's Q1 re-run follows on it (on the parallel stack, so the campaign economics stay the
~27 d/wave case rather than serial's ~48). RECURRENCE-DETECTED — the crash is gone or was
never the whole story, but the parity divergence remains, and the ladder proceeds to D-C
form 1 (`*CONTROLS` damping), which is the rung that targets the divergence and which
permanently un-reattaches both attempt-1 records when its spec field lands.
DIED-UNDIAGNOSED before w1400 — ADR-042 X2 allows exactly one re-probe.

### 6.58 SESSION 13 — D-C2: RECURRENCE-DETECTED. Four deaths, and the physics now has a name.

**The adapter bump fixed neither failure.** `hg2007_flexible_foil-20260907-155350` died at
**window 1996 of 8000** after 6847 s (1.90 h), same `corrupted double-linked list`, and the
detector fired at **w1820** — 176 windows of warning, the longest yet. Verdict:
**RECURRENCE-DETECTED**, terminal for the rung. Ladder: **3.89 h of the 35 h cap**.

**The score, four runs in:**

| run | scheme | adapter | detector fired | died |
|---|---|---|---|---|
| attempt 1 | parallel, contended | v2.20.1 | onset ~w1557 | w1703 |
| D-A | parallel, uncontended | v2.20.1 | w1460 | w1487 |
| D-B | **serial**, uncontended | v2.20.1 | — (grid starts w101) | **w88** |
| D-C2 | parallel, uncontended | **v2.20.2** | w1820 | w1996 |

**The divergence is in 3 of 3 parallel runs that lived long enough, and it is robust to
both the coupling scheme and the adapter version.** That is the signature of something in
the CASE, not in the coupling software — and the deck names the suspect.

**THE HYPOTHESIS THIS EVIDENCE POINTS AT: `*DYNAMIC, ALPHA=0.0`.** The solid deck
integrates with HHT-α at **α = 0.0**, pinned as ADR-039 gate clause C2 (*"ALPHA present
and 0.0"*). At α = 0 the scheme is Newmark average-acceleration: unconditionally stable
and **exactly zero dissipation at the Nyquist frequency**. The Nyquist mode of a
window-stepped solve is precisely a **period-2, window-alternating oscillation** — which is
the signature, named in advance by ADR-041's detector and observed three times. An
undamped Nyquist mode is not a bug in anyone's code; it is what this integrator does with
that parameter.

Two further observations consistent with it:

- **The diverging parity is not fixed.** attempt 1 and D-A diverged on the ODD branch;
  D-C2 diverged on the **EVEN** branch (odd 2.370 N against even 11.080 N at w1801-1820).
  Parity is just a label for which sub-step the mode started on — exactly what a Nyquist
  oscillation does, and not what a systematic odd-window code path would do.
- **D-C2 diverged LATER and more slowly** (w1820 vs w1460) at much lower absolute
  residuals, then still crashed. The adapter bump did not touch the mechanism.

**A CORRECTION TO §6.55's Fact 1, made because the record should not carry an inference
stronger than its evidence.** §6.55 read D-B's w88 death as showing the crash fires
independently of the divergence. That inference rests entirely on D-B — and D-B's solid
residuals were two to three orders of magnitude larger than D-A's from window 1, i.e. that
run was pathological from the start rather than a clean example of a healthy run crashing.
The weaker, better-supported statement: **in every run whose numerics stayed sane, the
divergence preceded the crash** (146, 27 and 176 windows of lead). The crash may well be
the divergence's consequence after all. ADR-042 X1's re-ordering was still the right call
on the information available — form 2 was cheap, it was the only executable form-2-shaped
change, and it has now been eliminated as a fix — but its stated rationale is weaker than
it read at the time, and that is recorded here rather than left to be re-derived.

**Next: D-C form 1, and it is now the physics rung rather than the leftover one.** It
targets exactly the parameter above. Two things make it the operator's decision rather
than an ordinary next step: it moves an **ADR-039 gate-clause expectation** (C2's
`ALPHA = 0.0`), which needs the same explicit declaration ADR-041 made for C1's coupling
scheme; and its new solid-spec field moves EVERY digest, permanently un-reattaching both
uncollected N3 attempt-1 records, the completed rigid arm included. It is also the LAST
pre-registered rung: if it fails V2, ADR-041 V1 gives a recorded NO-GO on infrastructure.

### 6.59 SESSION 13 — ADR-043 accepted; D-C1 IS RUNNING at CalculiX's own ALPHA default

**ADR-043** (`89a4a28`) pins the last rung: `*DYNAMIC, ALPHA=0.0` → **`ALPHA=-0.05`**, and
nothing else. The value was NOT chosen by taste — **-0.05 is CalculiX's own default**, read
out of the pinned source this container is built from (`CalculiX/ccx_2.20/src/dynamics.f:73`,
`alpha(1)=-0.05d0`, with the `[-1/3, 0]` clamp at :106-113). **ADR-039 C2's `ALPHA=0.0` was
a deliberate override of upstream's default to the single value in the permitted range with
exactly zero high-frequency dissipation** — and the Nyquist mode of a window-stepped solve is
a period-2, window-alternating oscillation, which is the signature seen in 3 of 3 parallel
runs, with the diverging parity flipping between them (ODD, ODD, EVEN) exactly as a Nyquist
mode would and a systematic code path would not.

Dissipation at `dt = 2e-5` s, α = -0.05 (ξ ≈ 0.025·ωΔt for small ωΔt):

| mode | ωΔt | energy lost per cycle |
|---|---|---|
| flapping, 0.986 Hz | 1.24e-4 | **3.9e-5** |
| 50 Hz structural | 6.3e-3 | 2.0e-3 |
| 500 Hz | 6.3e-2 | 2.0e-2 |
| **Nyquist, 25 kHz** | π | **~0.99** |

Against the observed growth of 1.027 per window, a per-step Nyquist decay of that order
turns growth into decay with a wide margin. V2's detector decides it.

**THREE THINGS THE IMPLEMENTATION GOT RIGHT AND A LATER READER SHOULD NOT UNDO:**

1. **The default writes the historical deck bytes.** `_alpha_text` renders `repr(0.0)` =
   `0.0`, NOT `_num`'s `0.0000000000000e+00`. Without it the unmitigated deck would have
   changed and ADR-043 Y2's "record move, not case move" claim would have been false.
2. **The gating fence grew a conjunct**: `is_campaign_configuration` = template-of-record
   AND alpha-of-record. One-way, like ADR-041 V7 — it can only refuse, and L5's five
   inputs stay necessary. Without it a rung at the gated five-tuple would mint a bundle
   claiming `gated=True` the moment B2's sentinels filled.
3. **The declared cost was paid, not dodged.** `hht_alpha` is a spec field, so every digest
   moved and **both uncollected attempt-1 records are now permanently unreattachable**, the
   completed 76 090-window rigid arm included. The pins were re-pinned per §6.44's rule
   (`bfc60a49…`→`0891e66d…`, `ed1ba571…`→`fae61ffa…`), the predecessors kept in
   `_SUPERSEDED` so the supersession stays checkable, and that test's docstring — which
   used to say "do NOT update the constant" — now says what it does and does not guard.
   Those runs' bytes remain readable on NFS and the rigid arm's residual table is already
   mined; nothing downstream reads them through `_reattach`.

**D-C1 IS RUNNING.** Submitted 2026-09-10 08:48 UTC:

```
run_id   hg2007_flexible_foil-20260910-084806
session  fsi-hg2007_flexible_foil-20260910-084806
submission  /mnt/aero-nfs/runs/hg2007_flexible_foil-20260910-084806/ladder-DC1-submission.json
```

8000 windows, flexible only, uncontended, 4 ranks, adr040-candidate, parallel-implicit,
`hht_alpha=-0.05`, `gated=False`, 24 h ceiling. **The deck that actually ran carries
`*DYNAMIC, ALPHA=-0.05, DIRECT`** — verified from the materialized bytes, not assumed.
Ladder spend before it: 3.89 h of 35 h.

**This is the LAST pre-registered rung.** ELIMINATED ⇒ the adoption commit moves ADR-039
C2's expectation and D10's rationale (ADR-043 Y3 declares both; the 2 % band itself does
not move) and V6's Q1 re-run follows. Anything else ⇒ **ADR-041 V1's ladder is exhausted
and the result is a recorded NO-GO on infrastructure**, which is a legitimate outcome.

### 6.60 SESSION 13 — D-C1 EARLY SIGNS ARE GOOD, and that creates a measurement problem

**Not a verdict — the run is ~5 % in.** Recorded now because the effect is large and
because the obvious way to "fix" the detector for it is a trap that a later session should
not have to re-discover.

**The early evidence is what the hypothesis predicted.** Per-window max solid residual,
same windows, damped against undamped:

| windows | D-A, α = 0.0 (max / median) | D-C1, α = -0.05 (max / median) |
|---|---|---|
| 1-100 | 1.90 / 1.6e-1 N | 1.89 / 1.5e-5 N |
| 101-200 | 1.97 / **1.04** N | 1.97 / **7e-6** N |
| 201-300 | 3.22 / **2.06** N | 5.5e-2 / **0** N |
| 301-400 | 4.07 / **3.23** N | 1e-6 / **0** N |

D-A's residual level CLIMBS with the ramp; D-C1's COLLAPSES after the startup transient.
The run is loaded and moving throughout (`average force= 5.04e-4`, disp increments
~3.4e-8), so this is convergence, not a force-free deck. It is also **2x faster** —
1.67 s/window against D-A's 3.25, i.e. ~3.7 h for the full span — consistent with the
solid needing far fewer iterations once the undamped Nyquist content is gone. **The
reading this supports: D-A's early residual level WAS the instability, not healthy load
response.**

**The problem this creates.** ADR-041 V2's parity prong needs both parities ≥ **1.0 N**
before a chunk counts, and ccx prints `largest residual force` with `%f` — six decimals —
so anything below 5e-7 N reads as exactly `0.000000` (67 % of D-C1's residual lines so
far). **A successful mitigation drives the observable below its own detector's floor**,
and V2(iii) then returns INCONCLUSIVE — correctly, since a ratio of near-zero quantities
carries no information, but INCONCLUSIVE is not ELIMINATED and cannot be adopted.
The floor was calibrated on runs we now suspect were already sick, so it assumes the sick
residual scale.

**THE OBVIOUS FIX IS A TRAP — tested against the known runs rather than assumed.**
ccx also prints `largest correction to disp` in SCIENTIFIC notation (7 significant
figures), so it escapes the quantization and looks like the natural substitute observable.
Its worst 20-window parity ratio, computed with no floor:

| run | verdict of record | worst parity ratio |
|---|---|---|
| attempt 1 | SICK, died w1703 | 5.00 @w1681-1700 |
| D-A | SICK, fired w1460 | 4.12 @w1461-1480 |
| D-C2 | SICK, fired w1820 | 11.27 @w1961-1980 |
| Q1 | healthy control | 1.01 |
| **D-C1** | **the run that looks healthy** | **42.51 @w201-220** |

D-C1 scores HIGHER than every sick run, because once corrections fall to 1e-9…1e-14 the
ratio is computed on numerical noise. The substitute needs an activation floor of its own
and then fails in exactly the same place. **No reinterpretation of V2 is available, and
none is being proposed.**

**What happens next is therefore: nothing clever.** The run has 95 % of its span left and
the commanded amplitude grows by roughly three orders of magnitude across it, so the
residuals may well rise back through the floor and let V2 evaluate exactly as written. The
rung is judged by the pre-registered rule when it lands, and only then is it worth asking
whether an INCONCLUSIVE-on-success outcome needs its own ADR. Proposing a detector change
from the first 5 % of a probe is precisely the post-hoc move this regime exists to refuse.

### 6.61 SESSION 13 — what the 1.0 N floor actually separates, computed BEFORE D-C1's verdict

Recorded now, while D-C1 is still running and its verdict is unknown, precisely because
the same numbers computed afterwards would read as rationalisation. Every figure below
comes from runs whose verdicts are already on the record — the healthy rigid control and
the two sick flexible runs — and none from D-C1.

**When does a run's per-window max solid residual first reach ADR-041 V2's 1.0 N
activation floor?**

| run | verdict of record | first window ≥ 1.0 N | commanded amplitude there |
|---|---|---|---|
| rigid control | healthy, completed all 76 090 windows | **w72261** | **100 % of full** |
| attempt 1 | SICK, died w1703 | **w127** | **0.0015 %** |
| D-A | SICK, died w1487 | **w135** | **0.0017 %** |

**The floor is not the noise floor it was written as.** V2 justifies 1.0 N as the level
below which "these are ratios of near-zero residuals, where a large ratio carries no
information" — true, and it is why the parity prong needs it. But empirically the floor
separates something else entirely: **a healthy solid does not reach 1 N until FULL
amplitude, while both sick runs were above it by window ~130, at 0.0015 % of amplitude.**
Four orders of magnitude of amplitude separate the two behaviours.

**Consequence for how a rung's activation fraction should be read.** ADR-041 V2(iii)
treats low activation as INCONCLUSIVE — "the detector is inert here, which is not the same
as health" — and that is the right default for a detector that can only compare parities.
But an activation fraction of ZERO across a span where **every sick run activated by
w135** is not the same evidential situation as a detector that never got data: it is the
run declining to do the thing the sick runs did, measured against a healthy control that
also declined to do it until 100 % amplitude.

**This does not change V2 and is not authority to.** V2's bounds are frozen, its verdict
on D-C1 will be whatever the pre-registered rule produces, and the rung will be recorded
under that rule. What this section establishes, ahead of the result, is that **if** D-C1
comes back INCONCLUSIVE-at-zero-activation, the honest reading of that outcome is a
question worth an ADR rather than a shrug — and the calibration that would justify one
already exists, in runs nobody can accuse of having been chosen after the fact.

### 6.61 SESSION 13 — a quantization-immune observable, derived BEFORE D-C1's verdict

**Written while D-C1 is still running (w~1313 of 8000), deliberately.** §6.60 recorded that
a successful mitigation puts the solid residual below ccx's six-decimal print precision and
therefore below V2's 1.0 N activation floor, and that the obvious substitute — displacement
corrections — fails because ratios of 1e-9-to-1e-14 quantities are noise. This section
derives a candidate that does not fail that way, and it is timestamped before the verdict so
that the derivation cannot have been fitted to it.

**The observable: ccx's final Newton iteration count per increment**, from
`hg2007-flexible-solid.sta` (last row per INC — `.sta` repeats INC once per coupling
iteration). Integers: no print precision, no floor, no near-zero ratios. **It is not a new
idea — it is §6.49's own evidence item 2** ("ccx Newton effort escalates in lockstep, odd
windows only: 39 windows with final ITER ≥ 8, ALL odd"), which ADR-041 cited as part of the
signature and then did not build a prong on.

| run | verdict of record | median ITRS | max | windows ≥ 8 | their parity |
|---|---|---|---|---|---|
| attempt 1 | SICK, died w1703 | 7 | 14 | 39 (w1625-1701) | **all ODD** |
| D-A | SICK, died w1487 | 6 | 12 | 5 (w1477-1485) | **all ODD** |
| D-C2 | SICK, died w1996 | 5 | 14 | 18 (w1960-1994) | **all EVEN** |
| Q1 | healthy control | 5 | 6 | 0 | — |
| **D-C1** | **α = -0.05, live** | **2** | **2** | **0** | — |

**Two properties make this more than a convenient number.**

1. **It reproduces the parity flip independently.** D-C2's residual divergence was on the
   EVEN branch where attempt 1's and D-A's were ODD (§6.58), and the high-iteration windows
   follow: all EVEN for D-C2, all ODD for the other two. An observable that tracks the
   mechanism's *phase* across three runs is measuring the mechanism, not the load.
2. **D-C1 is flat, not merely low.** Median 2 and max 2 in every 200-window band across all
   1313 increments so far — through the range where D-A already sat at median 6, and past
   nothing that looks like onset. It is cleaner than the HEALTHY Q1 control (median 5, max 6).

**This is corroboration, not a verdict, and V2 is not being reinterpreted.** D-C1 will be
judged by the pre-registered rule exactly as D-A, D-B and D-C2 were, with whatever it
returns. If that is ELIMINATED, none of this is needed. If it is INCONCLUSIVE-on-success,
then this table is the evidence base for an amendment adding an iteration-count prong —
calibrated on runs whose verdicts were already recorded, derived before the outcome it would
be used to interpret, and proposed to the operator rather than applied.

### 6.62 SESSION 13 — D-C1 COMPLETED 8000/8000. The rule says INCONCLUSIVE.

**The first flexible coupled run in this entire investigation to finish its span.**
`hg2007_flexible_foil-20260910-084806`, α = -0.05: `stopped_by=all-exited`, **both
participants rc=0**, **8000 of 8000 windows**, 20 287 s (5.64 h). Every predecessor died:
attempt 1 at w1703, D-A at w1487, D-B at w88, D-C2 at w1996 — four for four, three of them
carrying the parity divergence first.

**The solid went quiet by five orders of magnitude.**

| windows | D-A, α = 0.0 (max / median) | D-C1, α = -0.05 (max / median) |
|---|---|---|
| 101-2100 | died at w1487 | 1.97 / **0** N |
| 2001-4000 | — | 1.2e-5 / **0** N |
| 4001-6000 | — | 9e-6 / **0** N |
| 6001-8000 | — | 9e-6 / **0** N |

Over the whole run: p99 = **4.2e-5 N**, and exactly **2 windows of 8000** exceed 1.0 N —
both inside the startup transient before w200. D-A's median was **3.23 N and climbing** by
w301-400. It is also **faster**: 2.56 s/window over the last 1000 windows against D-A's
3.25, a 21 % improvement that lands directly on the campaign's economics.

**And the pre-registered verdict is INCONCLUSIVE.** 0 of 395 chunks reached V2's 1.0 N
activation floor, so V2(iii) fired: *"the detector is inert here, which is not the same as
health."* That is the rule working exactly as written — the parity prong can only compare
parities, and there was nothing above the floor to compare. **ADR-041's ladder, as
pre-registered, cannot adopt a mitigation that works**, because success removes the very
signal its only test consumes. Re-probing under V1(b) would return INCONCLUSIVE again for
the same reason: §6.61's calibration (committed at `95be432` BEFORE this result) shows the
healthy rigid control does not reach 1.0 N until **w72261, at 100 % amplitude**, and this
probe ends at 6 %.

**The verdict of record stands as INCONCLUSIVE.** It is not being reinterpreted, the floor
is not being moved, and the rung's evidence is on NFS under
`adr041-D-C1-{verdict.json,solid-residuals.tsv}`. What the result forces is a question the
pre-registration did not anticipate and cannot answer from inside itself: **how should a
completed full span with ZERO activation be read, when every run carrying the signature had
activated by window 135?** That is ADR-044's subject, and it goes to the operator with the
calibration that was timestamped before the data existed.

**Ladder spend: 9.53 h of the 35 h cap.** Box idle, nothing queued.

### 6.62 SESSION 13 — D-C1 COMPLETED 8000/8000. The crash is gone. V2 says INCONCLUSIVE.

**The first flexible run ever to finish its span.** `hg2007_flexible_foil-20260910-084806`
ran **8000 of 8000 windows**, `run_long` rc=0, both participants exited cleanly
(`Total CalculiX Time: 20287`, fluid `End` / `Finalising parallel run`), in 20 287 s
ClockTime = 5.6 h at **2.54 s/window**. Four prior flexible runs all died of
`corrupted double-linked list`; this one did not.

**Full span against the three that died — the last 200 windows each arm lived:**

| run | outcome | last-200 max residual | ITRS median / max | windows ≥ 8 |
|---|---|---|---|---|
| attempt 1 | died w1703 | **2.03e+03 N** | 7 / 14 | 39 (all ODD) |
| D-A | died w1487 | **3.54e+03 N** | 6 / 12 | 5 (all ODD) |
| D-C2 | died w1996 | **3.62e+03 N** | 5 / 14 | 18 (all EVEN) |
| **D-C1** | **COMPLETED 8000** | **0.00e+00 N** | **2 / 2** | **0** |

Over its whole span D-C1's median per-window residual is **0.000e+00** and its maximum is
**1.970 N** — the w101-200 startup transient, the same one every run shows. Newton effort is
**flat at 2 iterations for all 8000 increments**. The sick runs ended carrying residuals of
two to three thousand newtons and escalating Newton effort; this one ends at zero, having
gone four to five times further in windows.

**And the pre-registered detector cannot say any of it.** V2's verdict, computed by the
driver and recorded at `adr041-D-C1-verdict.json`:

> **INCONCLUSIVE** — 0/395 chunks active. "only 0.0 % of chunks reach the 1.0 N activation
> floor (V2 (iii) requires 50 %) — the detector is inert here, which is not the same as
> health"

That is V2 working exactly as written: a parity RATIO on near-zero quantities carries no
information, so it declines to call it health. **The floor was calibrated on runs that
carried the instability, and a mitigation that removes the instability removes the signal
the floor was sized against.** §6.60 recorded this risk before the run finished and §6.61
derived the way out before the verdict existed.

**V1's options, and why only one of them is honest.** An INCONCLUSIVE probe "has not spent
the rung's verdict and may be re-probed ONCE, after which a second INCONCLUSIVE becomes
UNRESOLVED". A re-probe would return INCONCLUSIVE again — the floor does not move because
the run is repeated. So the ladder's own machinery cannot convert this outcome into an
adoption, and D-C1 is the LAST rung: leaving it here means a recorded NO-GO on
infrastructure for a stack that just completed its span with the failure mode absent.

**Queued for the operator: an amendment adding the iteration-count prong** (§6.61's table,
committed at `9b6897a` BEFORE this verdict existed). It is integer-valued, immune to ccx's
six-decimal print precision, already part of §6.49's signature, and it separates all five
runs cleanly while independently reproducing the parity FLIP. Nothing is adopted and no
band moves until that amendment is accepted.

**Two things the record should carry into that conversation.**

1. **Adoption still requires V6's Q1 gate**, unchanged and with frozen bands. The one
   hypothesis this rung cannot rule out by itself is that the damping suppressed the
   PHYSICAL response along with the numerical mode; Q1 measures exactly that against the
   surviving ADR-039 baselines, and ADR-043 Y3 already declares what adoption moves
   (C2's expectation, D10's rationale, band unmoved).
2. **The economics may have improved.** 2.54 s/window here against D-A's 3.25 — 22 %
   faster, plausibly because the solid converges in 2 Newton iterations instead of 6.
   IF that ratio carried to the contended two-arm campaign shape it would take ADR-040's
   ~2.00 s/window projection to ~1.56, which is inside the 1.834 that 10 settled cycles
   need in 14 days — the first time any measurement has put a wave inside a two-week
   ceiling. **It is uncontended flexible-only and must not be treated as a campaign rate:
   only N3 may size that (ADR-040 N3).**

### 6.64 SESSION 13 — the .sta corroboration in ADR-044, INDEPENDENTLY re-derived

ADR-044's Z3 corroboration (added `a876938`) was re-parsed from the raw `.sta` files rather
than taken on trust, and the parser was cross-checked against session 12's own
`minerA_flexible.tsv` before being believed. **Every figure reproduces.**

| run | outcome of record | increments | median ITRS | max | ≥ 8 |
|---|---|---|---|---|---|
| D-C1, α = -0.05 | **COMPLETED 8000** | 8 000 | **2** | **2** | **0** |
| rigid control | COMPLETED 76 090 | 76 090 | **2** | 4 | **0** |
| Q1 control | healthy, 500 w | 500 | 5 | 6 | **0** |
| attempt 1 | SICK, died w1703 | 1 703 | 7 | 14 | **39, all ODD** |
| D-A | SICK, died w1487 | 1 487 | 6 | 12 | **5, all ODD** |
| D-C2 | SICK, died w1996 | 1 996 | 5 | 14 | **18, all EVEN** |

- **84 590 increments of healthy or completed coupled running contain ZERO windows at
  ITRS ≥ 8**; every run that died contains at least five.
- The **parity flip reproduces independently of the residual series**: attempt 1 and D-A
  all ODD, D-C2 all EVEN — matching each run's residual parity (§6.58), so the quantity
  tracks the mechanism's phase rather than the load.
- **D-C1 converges TIGHTER than the rigid control** (median 2 and max 2, against the rigid
  arm's median 2 and max 4) — the damped flexible arm behaves like the arm that never had
  the problem.
- Parser validation: 39 of 1703 increments at finalITER ≥ 8 for attempt 1, matching both
  §6.49's reported 39 and `minerA_flexible.tsv`'s own column. A first attempt at this parse
  read the wrong `.sta` columns (INC is field 1, not 0, and rows repeat per coupling
  iteration) and reported one increment per run; the number that matters is the one that
  agrees with session 12's table.

Why it is corroboration and not a rule: the count is integer-valued, so it has no
print-precision floor and no near-zero-ratio failure — the two things that silenced the
residual observable on D-C1. ADR-044 deliberately records it as EVIDENCE and adds no prong,
since adding an observable to a detector after seeing the run it would grade is the move the
regime refuses. **The decision still rests on Z1's conditions, which are keyed to zero and
to spans fixed before the result.**

**State: ADR-044 remains PROPOSED. Nothing is adopted, nothing has run since D-C1, the box
is idle, and the ladder stands at 9.53 h of the 35 h cap.**

### 6.65 SESSION 13 — ADR-044 ACCEPTED with Z4, and the re-probe it grades IS RUNNING

**The operator accepted ADR-044 on 2026-09-12 and chose Z4** (`d702b57`). Z1, Z2 accepted;
Z3 stands as recorded evidence and not as a prong; **Z4 taken**, which is the part that
matters most:

> **D-C1's completed run is NOT what gets adopted.** Z1 was implemented in code FIRST,
> then ADR-041 V1(b)'s single already-granted re-probe is spent, and THAT run is judged by
> the rule as accepted. The rule therefore predates the run it grades — the one defect in
> ADR-044 that care alone could not fix, since it was written after seeing D-C1.

D-C1's own verdict of record stays **INCONCLUSIVE permanently**. It is evidence, not the
adoption.

**Z1 in code** (`aero/vv/fsi/hg2007_flexible_foil.py`, `adr041_rung_verdict`): a probe that
COMPLETED its full span with **exactly zero** activation, contiguously, past
`ADR044_MIN_EVALUATED_WINDOW = 1350`. Each condition carries a test that states why it is
load-bearing — zero rather than "low" so the rule has no dial; completion, because a run
says nothing about the span it never reached; the window bar (10x w135, the latest window
at which any run carrying the signature had activated, fixed at `95be432` before D-C1's
verdict existed) so a short quiet span cannot pass; contiguity so zero is a measurement
rather than a gap; and a test that **a fired prong still fails** — Z1 only ever ADDS a
path, it never rescues a rung that diverged. Suite **1009 green**.

**THE RE-PROBE IS RUNNING.** Submitted 2026-09-12 16:13 UTC:

```
run_id   hg2007_flexible_foil-20260912-161321
session  fsi-hg2007_flexible_foil-20260912-161321
submission  /mnt/aero-nfs/runs/hg2007_flexible_foil-20260912-161321/ladder-DC1-reprobe-submission.json
verdict  python scripts/stage20_hg2007_flexible_foil.py --adr041-evaluate <submission JSON>
```

Identical shape to D-C1: 8000 windows, flexible only, uncontended, 4 ranks,
adr040-candidate, parallel-implicit, `hht_alpha=-0.05` (deck verified as
`*DYNAMIC, ALPHA=-0.05, DIRECT`), `gated=False`, 4 processor dirs, 24 h ceiling. ~5.6 h
expected. **Determinism is divergent (§6.49), so this is a genuinely fresh draw** — if
D-C1's clean completion was luck rather than mitigation, this is the cheapest thing that
exposes it. Ladder spend before it: 9.53 h of the 35 h cap.

**This is the rung's SECOND and FINAL probe.** ADR-041 V1 caps any rung at two under any
combination of V1(a), V1(b) and ADR-042 X2. Whatever it returns is D-C1's terminal verdict:
ELIMINATED under Z1 ⇒ adoption (ADR-043 Y3's C2 and D10 moves, `ALPHA_OF_RECORD` → -0.05,
then V6's Q1 re-run); RECURRENCE-DETECTED or a death ⇒ the ladder is exhausted and ADR-041
V1's **NO-GO on infrastructure** is the recorded outcome.

### 6.66 SESSION 13 — THE RE-PROBE IS ELIMINATED. The ladder has an adopted mitigation.

**`hg2007_flexible_foil-20260912-161321` — verdict ELIMINATED**, and it was judged by a
rule that existed in code before the run was submitted (ADR-044 Z4). That is the whole
point of the exercise, so it is worth stating precisely what happened in what order:

1. ADR-044 accepted with Z4 and **Z1 implemented** (`d702b57`), 16:0x UTC 2026-09-12.
2. Re-probe **submitted** 16:13 UTC.
3. Re-probe **completed** and evaluated: `stopped_by=all-exited`, both participants rc=0,
   **8000/8000 windows**, 20 818 s (5.78 h), **0 of 395 chunks active**, contiguous.
4. `adr041_rung_verdict` returned **ELIMINATED** via Z1, quoting its own conditions.

**It was a genuinely fresh draw, not a replay.** 1227 of 8000 windows (15.3 %) carry
different residual values from D-C1's — determinism is divergent (§6.49), so the two runs
explored different trajectories and both stayed quiet. Peak residual 1.886 N against
D-C1's 1.970 N; **one** window of 8000 above 1.0 N, against D-C1's two; both inside the
startup transient.

**The ladder's state is now closed:** D-A RECURRENCE-DETECTED, D-B DIED-UNDIAGNOSED,
D-C2 RECURRENCE-DETECTED, **D-C1 ELIMINATED on its second and final probe**. Ladder spend
**15.3 h of the 35 h cap**. The adopted mitigation is `*DYNAMIC, ALPHA=-0.05` — CalculiX's
own default, which ADR-039 C2 had overridden to the one value in range with zero Nyquist
dissipation.

**Adoption is now unblocked but NOT taken.** It is a commit, and per ADR-044 Z3 it
executes: ADR-043 Y3's moves (ADR-039 C2's expectation `0.0` → `-0.05`; D10's rationale
from exact-by-construction to bounded-by-dissipation, **the 2 % band unmoved**),
`ALPHA_OF_RECORD` → -0.05, and then **ADR-041 V6's Q1 re-run on the adopted stack** with
the frozen bands verbatim, before N3. ADR-040 W4 applies unchanged if Q1 rejects.

**What is still not proven, and the adoption does not claim:** why the heap corruption
stopped. Four runs died of it and two consecutive 8000-window runs on this stack did not.
§6.58's reading — that the crash followed the numerics going bad — is consistent and
remains unproven. V6's Q1 gate is also the first thing that can rule out the opposite
worry: that the damping is suppressing PHYSICS rather than only the Nyquist mode.

### 6.67 SESSION 13 — the GitHub failure notifications: aero-fleet DNS, not the science

The operator received a burst of failed-run notifications. **Diagnosed, and it is
infrastructure, not this branch's code or the solves.**

- `vv-required` and `vv-smoke` on PR #44 ran **11 h 29 m** and ended with GitHub's own
  *"internal error when running your job"*, conclusion `cancelled`, **runner name empty** —
  the signature of a job that queued and was never picked up.
- GitHub reports both self-hosted runners `aero-build-vv` and `aero-build-vv-2` as
  **offline**, while on aero-build both `actions.runner.*` services are **active/running**
  and the box has 21 days of uptime. Up locally, unable to reach GitHub.
- **Root cause: every aero LXC has no DNS.** CT 210-217 are all configured
  `nameserver: 192.168.2.1`, which **pings but serves no DNS**; `getent hosts github.com`
  fails on aero-build, aero-dev, aero-mlflow and aero-vv alike. **Technitium at
  192.168.2.209 resolves correctly** from the same containers
  (`github.com → 140.82.121.4`), and it is the LAN DNS authority per the homelab atlas.
  The post-move interim setup left the fleet pointed at the gateway instead.
- **It predates this session**: no `vv-smoke` success in the last 40 runs, back to
  2026-09-04. The many notifications are this session's pushes each queueing a job that
  could never run.

**No aero science was affected.** Solves reach aero-dev by IP over SSH and NFS by IP; the
re-probe completed cleanly through the whole outage. The CalculiX rebuild also survived it
because that build is split-host by design — buildah on the Proxmox host, which has working
DNS, then apptainer on aero-build from a local OCI archive with no network in `%post`.

**What it DOES block: `vv-required` is a stage-gated REQUIRED check on PR #44.** While the
runners cannot reach GitHub, that check cannot pass and the PR cannot merge.

**The fix is a host-side `pct` change and therefore the operator's** (CLAUDE.md Hard Rule 5
and the provisioning gate): point the aero LXCs at 192.168.2.209. It is packaged, not run,
at `net-ops/scripts/fix-aero-lxc-dns.sh`. Applying it means an atlas update and
`atlas-refresh.sh` in the same session.

### 6.68 SESSION 13 — the fleet DNS fixed, the mitigation ADOPTED, and V6's Q1 gate running

**Infrastructure (operator-approved, applied 2026-09-13).** All eight aero containers
(CT 210-217) moved from the dead resolver `192.168.2.1` to Technitium `192.168.2.209`.
Two things the first pass got wrong and the record now carries:

1. **`pct set --nameserver` alone does not fix a RUNNING container** — PVE writes
   `/etc/resolv.conf` at container START, and `resolvconf -u` does not apply (it is a plain
   file). The live file had to be rewritten in place; PVE regenerates identical content from
   the corrected config on the next boot.
2. **GitHub had already DELETED both self-hosted runner registrations** ("automatically
   deleted for runners that have not connected recently"), so DNS alone left them dead.
   Re-registration was needed, and `config.sh` refuses with *"already configured"* until
   `config.sh remove --local` clears a leftover `.runner_migrated`. Both runners are now
   **online** and picking up work.

Script: `net-ops/scripts/fix-aero-lxc-dns.sh` (dry-run by default, updated to match what was
actually required). Atlas updated and refreshed (`homelab-atlas` `8ab673b`).

**THE MITIGATION IS ADOPTED** (`712745b`). `ALPHA_OF_RECORD` = **-0.05**, and the builder
and CLI defaults follow it so `--submit-040` — which builds its own spec from five arguments
and cannot be handed alpha — produces the adopted configuration. `LEGACY_HHT_ALPHA` stays
**0.0 permanently** and `_reattach` still supplies it, so no historical record silently
re-describes itself as mitigated. The two live digest pins now name `hht_alpha: 0.0`
EXPLICITLY rather than inheriting a default that has moved; their digests are unchanged.
ADR-043 Y3's two declared moves are executed and recorded there: ADR-039 C2's expectation
`0.0` → `-0.05`, and D10's rationale from exact-by-construction to bounded-by-dissipation
with **the 2 % band unmoved and D10 still gated**. Suite **1010 green**.

**V6's Q1 GATE IS RUNNING** — the first thing that can rule out the worry the ladder cannot:
that the damping suppresses PHYSICS rather than only the Nyquist mode.

```
flexible  fsi-hg2007_flexible_foil-20260913-093428
rigid     fsi-hg2007_rigid_foil-20260913-093449
record    python scripts/stage20_hg2007_flexible_foil.py --record-q1 <flex> <rigid> \
            --out data/vv/stage20_q1_equivalence_adr041.json
```

Both arms **concurrently at 4+4** (verified on the box: 8 `pimpleFoam`, 2 `ccx_preCICE`),
500 windows at dt 2e-5 — the same shape the accepted Q1 candidate ran, recovered from its
own deck (`2.0000000000000e-05, 1.0000000000000e-02`) rather than assumed — adr040-candidate
numerics, `hht_alpha=-0.05`, ~45 min. **The three bands are ADR-040 Q1's verbatim**: 2 % on
the span-mean, 5 % of baseline peak-to-peak on the trace, 5 % on the flexible-minus-rigid
increment, against the same surviving ADR-039-numerics baselines
`hg2007_flexible_foil-20260810-144742` / `hg2007_rigid_foil-20260810-144747`.

**The record goes to a NEW path** (`stage20_q1_equivalence_adr041.json`); the accepted
unmitigated record is never overwritten. **If it rejects, ADR-040 W4 applies** — the stack
is inadmissible, no band widens, and the declared alternatives go to the operator.

## 7. Open items for the next stage (and beyond)

**SESSION-13 RESUMPTION PATH (2026-08-29 — supersedes the SESSION-12 path below; §6.49).**

### READ §6.49 FIRST. N3 IS NOT RUNNING. THE MITIGATION-ADR DECISION IS QUEUED WITH THE OPERATOR.

**The operator-paste prompt for session 13 is committed at
`docs/handoff-bundle/STAGE-20-SESSION-13-PROMPT.md`** — it carries the endorsed ADR-041
ladder path (D-A unmitigated+observability / D-B serial-implicit / D-C fallback, adoption
rule, Q1 re-run on the winner) agreed at session-12 close-out, and supersedes the
option-space framing below in detail while changing none of it in substance.

- Session 12 executed the SESSION-12 path's first item (mine the dead arm's logs) and
  STOPPED at that path's own stop rule: the mining verdict is **MITIGATION-WARRANTED**
  (§6.49) — a 150-window period-2 precursor inside CalculiX, adversarially verified,
  evidence + parsers at `/mnt/aero-nfs/runs/stage20-n3-attempt1-mining/`.
- State: aero-dev IDLE, nothing submitted, **B0 untouched at 134 h**, suite 962
  green + mypy clean at `b9fd72c`, both attempt-1 runs and all prior artefacts untouched.
- Next, in order: (1) the operator picks among §6.49's options (a)-(d); (2) if (a)/(b)/(c),
  write the mitigation ADR — it must record the byte/config/container diff, the
  config_hash or container-SHA move (ADR-037 precedent), that Q1 was measured on the
  unmitigated stack, and the digest-pin re-pin; (3) re-run N3 both arms detached under B0
  (~82 h binding arm vs 96 h per-submission; the §6.46-item-3 stop rule stands: one arm
  dies pre-ramp ⇒ `run_long.sh kill` the partner and record both); (4) everything
  downstream of a landed contended N3 is UNCHANGED from the SESSION-12 path below —
  collect-probe both arms → fine-rung I7 probe → B3 ceiling BEFORE B2 → `--size-040` →
  fill in the commit that ADDS `data/vv/stage20_n3_confirmation.json` → wave 1.
- Submission mechanics for step (3), verified against the driver this session: `--probe
  <arm> mid --probe-dt 2e-5 --probe-windows 76090 --ranks 4 --numerics adr040-candidate
  --timeout 345600 --out <f>` — the `--timeout`/`--numerics`/`--ranks` defaults (43 200 s
  / adr039-baseline / 1) all silently sabotage the run if omitted. Copy both submission
  JSONs to `/mnt/aero-nfs/runs/<run_id>/n3-submission.json` immediately (attempt 1's are
  there as the pattern). Poll `run_long.sh status root@aero-dev fsi-<run_id>` +
  `--project-n3`; NEVER `run_long.sh wait`.

**SESSION-12 RESUMPTION PATH (historical: its first item is done — §6.49 — and its re-run
step is gated on the operator decision above; corrected 2026-08-15 — §6.48).**

### READ §6.46-§6.48 FIRST. The rigid arm is DONE, the box is idle, and W6 is not in play.

State at the 2026-08-15 audit, all verified against the runs' own bytes:

- `fsi-hg2007_flexible_foil-20260812-230102` — `failed`, CalculiX heap corruption at
  window 1703 of 76 090, `stopped_by=participant-died` (§6.46). Its 1703 windows of
  `Solid.log` are on NFS, unmined.
- `fsi-hg2007_rigid_foil-20260812-230109` — **COMPLETED 2026-08-14 05:57**, all-exited,
  rc=0 both participants, all 76 090 windows in 30.9 h; post-ramp **1.296 s/window**.
  A diagnostic, not a sizing input: uncontended and single-arm.
- The §6.47 discriminator RESOLVED: **candidate 1 refuted** (10.2× the factorisations,
  zero corruption — §6.48 item 2). The abort is specific to the flexible arm's
  deformation.
- **W6 does not bind here** (§6.48 item 3): the N3 re-run is an ordinary probe under B0,
  which has **134 h remaining**. Wave 1's one-resubmission protection is untouched.
- Nothing is running on aero-dev. The rack may be POWERED OFF for the house move — check
  `net-ops/docs/shutdown-restart-runbook.md` and run post-boot-verify before assuming the
  cluster exists.

**The first item is the ccx abort, and it is diagnosis, not budget.** If the abort recurs
on a re-run, the campaign is infeasible on this ccx build without a mitigation ADR — so:
mine the dead arm's `Solid.log` for the deformation signature (trend in `no convergence`
retries toward the abort, element-quality or Jacobian warnings, deck vs displacement
magnitude), THEN re-run N3 both arms under B0 (projected ~82 h binding arm, inside the
96 h per-submission ceiling), with `--project-n3` polled at the ramp boundary (~52 h). A
recurrence is a real result: stop, write the mitigation ADR (deck bytes will move the
spec digest — the ADR-037 precedent), and only then spend more box time.

**Once a contended N3 has landed:**

**Then, in order:**

1. **`--collect-probe` both N3 arms** once they finish, `--out` into `/tmp`, then
2. **the fine-rung I7 probe — NEW, and it is a real item, not a footnote** (see below), then
3. **bring the operator the measured post-ramp rate and take the B3 ceiling decision**
   (RESUME §7 item 5) — BEFORE B2 is filled, then
4. **`--size-040 <flex bundle> <rigid bundle> <fine bundle> --ceiling-s <approved>`** and
   read its refusal or its numbers, then
5. **fill B1/B2/B3 and the four `GATED_040_*` sentinels** in the commit that ADDS
   `data/vv/stage20_n3_confirmation.json` (RESUME §7 item 7), with
   `tests/unit/test_adr040_budget_is_derived_from_n3.py` re-deriving them through
   `size_gated_campaign_040`. The file must be a NEW path: `_merge_base_guard_040` resolves
   add-commits with `git log --diff-filter=A`, and ADR-040's add-commit is `d5bf381`.
6. **wave 1** via `--submit-040`, submit only, no owning wait.

### THE FINE-RUNG I7 PROBE — required by the sizing rule, and it can only run after N3

`size_gated_campaign_040` builds
`required = [(arm, rung) for arm in arms] + [(arms[0], fine_rung)]` →
`[("flexible","mid"), ("rigid","mid"), ("flexible","fine")]` and refuses
(`hg2007_sizing.py:441-449`) with:

> `no I7 probe for arm='flexible' rung='fine' - dt is fixed across rungs (ADR-039 B2,`
> `carried over by ADR-040 U3), so the fine rung's Courant bound must be measured, not`
> `assumed from the ratio`

`data/vv/stage20_i7_courant.json` carries **mid-rung probes only**, and N3 is mid-rung on
both arms. So `--size-040` on the two N3 bundles refuses at this clause today — verified,
and pinned by `test_the_missing_fine_rung_probe_is_refused`. Four things about it:

- **it runs AFTER N3, never alongside.** N3's value is a contention-measured rate; any
  other solve on aero-dev corrupts the one number B2 is sized from;
- **it must share the mid-rung probes' dt exactly.** dt is fixed across all three rungs so
  temporal error is common-mode (I8), and the rule refuses a probe set carrying two dts;
- **it must COMPLETE** its requested windows and end `stopped_by="all-exited"`.
  `_require_complete` still applies to probes, even though ADR-040 W3 relaxed it for
  confirmations;
- **it must reach the post-ramp window to have a `max_courant_post_ramp` at all** — at
  least 50 726 windows — so it is itself a multi-day run at the fine rung's cell count.
  This is the same arithmetic that made ADR-039's B1 never satisfiable, which is why B1
  reads `<<B1-PENDING-N3>>`. **Budget for it explicitly when taking the B3 decision.**

`--collect-probe` already emits both the `i7` and `i4` blocks from one run, and
`--size-040` takes `nargs="+"`, so the fine bundle needs no new flag.

### What session 11 landed

Five commits, `2a90489`..`c774475`, **962** tests green (was 883), mypy clean:
the live-N3 digest pin (alone, first); `i7_probe_from_bundle` /
`n3_confirmation_from_bundle` in `aero/vv/fsi/hg2007_sizing.py`; the `--size-040` driver
mode with the full refusal battery; `read_arm` executed end to end for the first time on
any input; the join re-derived on decomposed bytes; and this record.

**Nothing was filled.** B1/B2/B3 still carry their sentinels, the four `GATED_040_*` are
still `None`, `data/vv/stage20_n3_confirmation.json` still does not exist, and status stays
`partial`. No tag, no verdict.

**Nothing ran on aero-dev** beyond `run_long.sh status` and the `cat rc` inside `_reattach`.
Q1 and L-smoke artefacts are untouched at
`/mnt/aero-nfs/runs/hg2007_*_foil-20260812-21{4956,5900,5908}`.

---

**SESSION-11 RESUMPTION PATH (historical; session 11 executed it).**

### N3 IS RUNNING. POLL IT BEFORE ANYTHING ELSE.

Submitted detached 2026-08-12 23:01 UTC, both arms concurrently, 4 fluid ranks each,
`adr040-candidate`, dt 2e-5, 76 090 windows (`t = 1.5218 s`), B0 ceiling 96 h. **Do not
hold an owning `wait`** — `AERO_RUN_LONG_REAP=1` makes `wait` the owner of the job's
lifetime and would kill it.

```bash
scripts/run_long.sh status root@aero-dev fsi-hg2007_flexible_foil-20260812-230102
scripts/run_long.sh status root@aero-dev fsi-hg2007_rigid_foil-20260812-230109
scripts/run_long.sh logs   root@aero-dev fsi-hg2007_flexible_foil-20260812-230102
```

The submission JSONs are on NFS beside their runs, because a scratchpad does not survive a
session:

```
/mnt/aero-nfs/runs/hg2007_flexible_foil-20260812-230102/n3-submission.json
/mnt/aero-nfs/runs/hg2007_rigid_foil-20260812-230109/n3-submission.json
```

**Check the projection before waiting on it** (read-only, safe on a live run — §6.41):

```bash
python scripts/stage20_hg2007_flexible_foil.py --project-n3 \
  /mnt/aero-nfs/runs/hg2007_flexible_foil-20260812-230102/n3-submission.json
```

Then collect with `--collect-probe <submission>`, which now emits an `n3` block carrying
the post-ramp rate whenever the run cleared the ramp. **Projected 78.0 h to completion; the
ramp clears at ~52 h.** Expect it to still be running.

**Then, in order:** RESUME §7 item 6 (re-run the pre-flight under ADR-040 — I1/I3/I8/I9 are
CITED, never re-run), item 5 (bring the operator the measured post-ramp rate and take the
B3 ceiling decision BEFORE B2 is filled), item 7 (fill B1/B2/B3, land
`tests/unit/test_adr040_budget_is_derived_from_n3.py`, and put the calibration in the NEW
file `data/vv/stage20_n3_confirmation.json` — `_merge_base_guard_040` resolves with
`git log --diff-filter=A` and ADR-040's add-commit is `d5bf381`), then item 8, wave 1, via
`--submit-040`.

**What session 10 landed** (9 commits, `5de422b`..`fc47322`, **883** tests green, mypy
clean): the ADR-039 digest pin; the parallel seam; **ADR-040 `accepted`**; spec knobs v2 +
`--submit-040`; the L-smoke PASSED on the real coupled deck; **the readout fix, proved
against both surviving I4 arms**; **Q1 ACCEPTED**; B0 raised to 96 h on the measurement;
`--project-n3`; and this handoff.

**As predicted at session open, RESUME §7 items 5-8 did not land** — every one of them
waits on N3, and N3 needs 78 h. What did land beyond the plan: the readout fix moved ahead
of N3 rather than behind it, Q1 ran before N3 (operator decision, same argument as the
L-smoke), and two latent collector faults were found by running the code (§6.39).

**Nothing else is running on aero-dev.** The Q1 and L-smoke artefacts are at
`/mnt/aero-nfs/runs/hg2007_*_foil-20260812-21{4956,5900,5908}`; session 9's
`stage20-screen9` and session 8's `stage20-screen` are untouched.

---

**SESSION-10 RESUMPTION PATH (historical; session 10 executed it).** Session 9 closed the
attribution question and settled the two knobs ADR-040 could not have pre-registered
honestly without measuring. `docs/handoff-bundle/STAGE-20-RESUME.md` §6e + §7 is the map;
§6.34-§6.36 above are the evidence. In one line: **both named leads are refuted, the 3x is
the coupling's permanent cold start and not the mesh, the rank count is 4 and not 6, and
`--collect` would have raised after wave 1's weeks of wall clock.**

Landed and pushed (5 commits, `bc24e08`..`c4069bc`, **789** tests green, mypy clean):
`scripts/stage20_numerics_screen.py` (the harness session 8 never committed, plus the
variable it could not vary), `data/vv/stage20_n4_deforming_screen.json`,
`tests/unit/test_stage20_n4_deforming_screen_record.py` (13 tests), and §6.34-§6.36 here.

**NOT started: ADR-040 itself, the parallel launcher seam, the readout fix, the equivalence
probe, the coupled confirmation, wave 1.** Session 10's order is RESUME §7 items 1-8 as
rewritten there, and the ordering rationale is that **N3 is the only multi-day item** — get
it submitted, then do local work while it burns.

Screen artefacts are on NFS at `/mnt/aero/runs/stage20-screen9` (session 8's
`stage20-screen` is untouched and is still the evidence behind the N2 record). Nothing is
running on aero-dev.

Landed and pushed (7 commits, `24efcdc`..`c753321`, 774 tests green):
`solver_log.read_fluid_cost_history` + `aero/vv/fsi/cost_model.py` (the instrument), the
driver's `--collect-cost`, `data/vv/stage20_i10_cost_split.json` and
`data/vv/stage20_n2_screening.json` (the evidence), the `fvSolution` byte-pin, and
`FluidNumericsSpec` on the spec (the provenance hole — two numerics hashed identically).

**NOT started: ADR-040 itself, the parallel launcher seam, the equivalence probe, the
sizing fork, the coupled confirmation, wave 1.** Session 9's order is RESUME §7 items 1-8.

Screening artefacts are on NFS at `/mnt/aero/runs/stage20-screen` (224 MB, 18 case copies
+ their logs). The `.log` files are the evidence behind
`data/vv/stage20_n2_screening.json`; the case directories can be reclaimed once ADR-040
lands. Nothing is running on aero-dev.

**Kept as history below (the session-8 path, now complete):**

1. **ADR-040 — re-pre-register the campaign numerics against §6.29's measurements,
   BEFORE any campaign run.** Honest because no gated campaign ever ran; ADR-039's
   FORBIDDEN list binds post-campaign changes, and its own P4 mechanism (sentinels None,
   sizing refuses) is what stopped the launch. The design space, each option with the
   §6.29 arithmetic it must beat (14 d/wave at >= 10 settled cycles => <= ~2 s/window,
   i.e. >= a 10x-30x improvement on the measured 19 s/window flexible):
   - **Fluid subcycling inside the coupling window** (the standard preCICE resolution):
     window size back at O(3.5e-4) — 67k windows/campaign — with the fluid taking K
     internal Euler steps per window at dt_f <= 2e-5. Coupling overhead amortizes ~17x;
     PIMPLE cost stays. Requires: the deck's `DIRECT dt == window` stays TRUE (the SOLID
     still steps per window), but `FlexibleFoilSpec`'s `deltaT == time_window_size`
     identity, C2's wording, the force-cadence classifier and the readout's
     one-row-per-window assumptions all need revisiting — a real pre-registration, not a
     knob.
   - **Parallel fluid participant** (decomposePar + parallel pimpleFoam under the
     adapter): I1 proves MPI_Init works in-SIF; Stage 19 simply ran serial. 8-way could
     buy ~4-6x on the PIMPLE share alone. Measure the §6.29 cost split first.
   - **forces1 write scheduling**: the interface-power FO needs the force field
     REGISTERED (execute-time), not serialized every step; if `writeControl` can drop to
     `writeTime` without starving the FO, the per-step NFS writes vanish. Verify against
     the coded FO's lookup semantics before touching the frozen deck bytes.
   - **The rung family's TE cells** (19 um at n_te=4) are the Courant binder; any change
     re-opens M4's counts and the GCI ladder — the most invasive option, last resort.
2. **Then re-run the pre-flight ladder under ADR-040** (I7 at the new numerics, I4 at
   campaign shape, fine-rung Courant), fill its B2, and launch wave 1 detached via the
   session-7 driver (`--submit`, `--collect`; the seam and modes are built and tested).
3. **Carry-forward measurements that stand regardless**: I1/I3/I8/I9 records
   (`data/vv/stage20_*.json`), the Euler decision, the D10-residual convention, the
   1.2M-row amplitude bound, and the review-hardened deck/template/readout gates.

**Blocking, in order — this is the resumption path**

1. ~~Finish the figure digitization~~ — **DONE 2026-07-31.** `digitization.csv` (208 markers,
   Figs 5.6a/b/c + 5.9a + 5.13a), `hg2007_recomputed.csv` (the reference of record),
   `scripts/stage20_digitize_hg_figures.py` and `scripts/stage20_acquire_hg_reference.py`.
   **R2 PASSES** on all five anchors — pitch amplitude 16.99° vs 17° (−0.1 %) and 5.48° vs 6°
   (−8.6 %), crossover at Re 18000/27000, and both increments positive — with the one documented
   disagreement in §6.8. Three readings per marker are three independent *binarizations* of a
   cross-correlation match against each figure's own legend glyph, declared as a deviation from
   "three human passes" and strictly more auditable (anyone can re-run it).

   **The gated operating point is fixed** (from the reference alone, before any solve):
   **Re = 9000, St = 0.345, flexible `b/c = 0.85e-3` (76.5 µm) vs rigid `b/c = 4.23e-3`
   (380.7 µm)** ⇒ `U = 0.1 m/s`, `f = 0.9857 Hz`, `T = 1.0145 s`. Reference values:
   `C_T` 1.008 / 0.398 (`ΔC_T` = 0.609), `η` 0.1753 / 0.0888 (`Δη` = 0.0865), pitch amplitude
   5.35°. **Re = 9000 is forced** — Fig 5.13 exists only there, so it is the only Re at which the
   D0 structural gate has a reference at all.

   **The selection rule changed and ADR-039 must record why.** The originally approved rule
   ("largest measured `ΔC_T`") is degenerate: `C_T` scales as `St²`, so `ΔC_T` rises monotonically
   to the figure's right-hand edge (it peaks at St = 0.89, where f = 2.54 Hz is the top of the
   rig's stated 0.3–2.5 Hz range and peak plunge velocity is 2.8× freestream). That is exactly why
   HG plot `C_T/St²`. The operator-chosen replacement maximises **`Δ(C_T/St²)` inside the
   `0.2 < St < 0.4` band the thesis itself calls out** as observed in nature and containing its own
   efficiency optimum (St = 0.29). Note the optimal plate thickness **moves with St** — the thesis
   says so, and the digitization reproduces it — so plate and Strouhal number are chosen together.

1b. **The mesh feasibility spike PASSED; the thin-plate fallback is not needed.** Both arms mesh
   at the chosen `b/c = 0.85e-3`: `checkMesh` "Mesh OK", 48 240 cells, skewness 2.40/2.39, no
   negative volumes. `CaseSpec.section` (`TeardropPlateSection`) swaps only the surface curve the
   existing eight-block C-grid wraps, so the grid stays self-similar under refinement and a real
   3-grid GCI remains admissible. The NACA path is pinned byte-identical by test. **But read §6.9
   before writing I5.**
2. ~~Apply Postgres migration `005_container_set`~~ — **DONE 2026-07-31**, see §4. The multi-container
   mirror path is clear; nothing else in the provenance chain blocks the campaign.
3. **Run `scripts/grant_aero_build_ssh_to_aero_dev.sh`** (operator; packaged, not executed —
   authorising a remote root key is the class auto-mode blocks by design). Runbook at
   `docs/operator/aero-build-to-aero-dev-ssh.md`. **Not on the campaign's critical path**: the
   campaign is launched by hand from the Proxmox host, which reaches aero-dev already. This unblocks
   *CI* reaching the 16-core box — including `test_unsteady_plunging_airfoil`, which has never
   completed there.
3b. ~~**Phase 3A's non-regression pins are DONE (`67d8e82`); the refactor they protect is NOT.**~~
   — **DONE 2026-08-04 at `1bd7011`.** The ordering held and is checkable:

       git merge-base --is-ancestor 67d8e82 1bd7011              # true
       git diff --stat 67d8e82 1bd7011 -- tests/stage_20/fixtures/   # EMPTY
       git diff --stat 67d8e82 1bd7011 -- tests/stage_20/test_stage19_load_path_unchanged.py
                                                                 # EMPTY

   The goldens were not re-captured, the load-path pin is untouched, and the materialization pin
   changed only in how it CONSTRUCTS a spec — not one assertion moved. `MaterializedTree` carries
   one `source` field rather than the specified XOR pair (§6.14). **The FSI3 `config_hash` moved,
   as predicted: `c524faff...` -> `3f94f394...`**, pinned by test with the old value in the
   docstring; ADR-037 must record both and say plainly that the materialized *bytes* are proved
   identical while the *spec serialization* moved — different claims.

   Also landed: **`10fcb70`** — the additive `PreciceConfigExpectation` extension (15 fields, all
   defaulting to "do not check", each driven with a wrong value in a parametrized test; ordered
   `mappings` tuple; an `UNSET` sentinel so "assert absent" is distinguishable from "do not check";
   and `max_time`, which the plan omitted but which an authored case must assert because there it
   is a rendered token rather than the one permitted mutation). And **`c682671`** — the
   `transient_fvschemes` byte pin, on pre-change code, because the one the prompt cites does not
   exist (§6.15).

   ~~Old text follows for context.~~ Formerly:
   The two tests, their fixtures and their goldens landed in a single commit on pre-refactor code,
   which is the ordering rule the stage turns on. Prove it before trusting the refactor:

       git log --oneline -- tests/stage_20/fixtures/          # must be exactly 67d8e82
       git merge-base --is-ancestor 67d8e82 <refactor sha>    # must be true

   Still to do, in one commit: `CoupledCaseSpec.source: TutorialSource | AuthoredSource`
   (discriminator `kind`); `TutorialTree` -> `MaterializedTree` (`pin` XOR `authored`);
   `DeclaredMutation.kind += "authored"` with `before_sha256: str | None`;
   `select_fluid_mesh(fluid_participant_dir=...)`; `_materialize` as a **method**;
   `CASE_ROOT_DIRNAME` + `_case_dir()`; and the `_assert_status_gate` / `_assert_coupling_
   converged_over` extraction. Note the site count: **7 production + 2 test literals**, not eight.

   **Keep the manifest bytes identical by versioning the SHAPE, not by adding fields.** Extract
   a pure `render_tutorial_manifest_json(...)` (schema v1, dicts built by hand from explicit
   fields, never `model_dump()`) whose docstring says its bytes are a committed golden reproduced
   in every pre-Stage-20 bundle; give authored cases a *separate* emitter. `json.dumps(sort_keys=
   True)` is recursive, so a single new optional field on `MaterializedFile` or `DeclaredMutation`
   rewrites all 94 `files` entries, and a new top-level key re-sorts the document. Keep `dest` at
   `host_path/CASE_ROOT_DIRNAME` and assert `tree.root.name == CASE_ROOT_DIRNAME` in a validator,
   or `case_dir` and every mutation `path` shift.

4. ~~**Author the coupled case**~~ — **the WRITERS are all DONE (session 5, `397af1c`..`b9f317f`).**
   Landed, each with its own re-reader or assertion: the digest-pinned `precice-config.xml`
   template + renderer (`aero/adapters/precice/template.py`); the CalculiX `.inp` writer +
   re-reader + `config.yml` reader (`aero/adapters/precice/calculix.py`); the dimensional
   fluid deck (`aero/adapters/openfoam/flexible_foil.py`) with the adapter function object,
   both wall patches everywhere, fixed `dt` and `timePrecision 12`; the interface-power
   object (P2); the promoted force readers with `n_dropped`
   (`aero/adapters/openfoam/force_io.py`); `ddt_scheme=` on `transient_fvschemes`; the
   per-cycle objects and prescribed period on `analyse_limit_cycle`; the cross-arm checks
   and efficiency helpers (`aero/vv/alignment.py`); and the `.dat` reader with structural
   cadence classification (`aero/adapters/precice/ccx_dat.py`).

4b. ~~**WHAT IS LEFT OF IT — the next commit, fully specified.**~~ — **DONE 2026-08-06 at
   `227ffed`.** `_materialize` and `_render_manifest` dispatch exhaustively on the source
   kind; an authored spec writes 18 files, each re-read; the schema-v2 manifest carries
   `spec_sha256` computed by CALLING `config_hash` (not `sha256(model_dump_json())`, which is
   a different number — sorted keys, no whitespace).

   **The provenance decision was taken as specified: the physical spec rides ON
   `AuthoredSource`.** `config_hash` is computed over the serialized spec, so anything built
   inside the materializer is invisible to it — and the rung knobs, the wall spacing and the
   plate thickness are all inputs no bundle could otherwise recover. Cost: `case.py` imports
   the OpenFOAM and CalculiX writers, which every `launcher.py` consumer inherits (~250 → ~457
   modules). **Module weight, not correctness** — traced step by step, no cycle, no banned
   dependency, and the fence names both. Rejected alternatives, for ADR-037:
   derive-at-materialization (the rung knobs leave `config_hash`, so the three GCI rungs would
   hash identically — a strictly worse hole than the one being closed), and a canonical-JSON
   string plus digest (defeats `extra="forbid"`, and duplicates what `config_hash` already
   covers).

   Carrying both specs on one object is also what made §6.25's three checks possible at all.

4c. **The V&V case object — DONE 2026-08-06 at `21840e0`.** `aero/vv/fsi/hg2007_readout.py`
   (the only module importing both adapters) and `hg2007_flexible_foil.py`. `read_arm` calls
   `solver.load()` FIRST and takes its analysis window from the returned `SolveResult`, so K2,
   C4 and K1 have run before any number exists and the window cannot be widened — the gate is
   structural, not conventional.

   **Both arms are registered as separate cases.** `evaluate` sees one result, so `metrics()`
   carries only what one arm can measure and the D3/D4 increment is the driver's. Registering
   each arm is what stops one going quiet in the registry-driven report. **ADR-039 must state
   that the increment has no dashboard row.**

   **No default time step, deliberately.** `GATED_TIME_WINDOW_S` / `GATED_MAX_TIME_S` are
   `None` until ADR-039 B2 records the I7 and I4 measurements, and `is_gated_configuration`
   returns `False` while they are. `gated` is DERIVED, so **no configuration can claim the
   gated verdict before the pre-flight has run.**

5. **ADR-039, before any campaign run.** Families P/C/I/R/K/S/**A**/D/**M**/X, byte-bound to the
   driver, with the two deliberate improvements on ADR-036: every gated clause named in the VERDICT
   line (ADR-036 omitted S5 — the clause its own review had just added), and a shape-7 test
   asserting every clause identifier is either in the VERDICT line or the reported-only list.
6. **Pre-flight + I4**, then the campaign. **Do not extrapolate a rate from the transient**: Stage
   19 was off by 3.5-9.6× in one direction and the B3 diagnostic by ~1.8× in the other.

   **Three probes are already done** (session 5, pulled forward): **S1** — the ccx spike, see
   §6.17/§6.18/§6.19; **I6** — the coded FO compiles under `setpriv --reuid 1000` and its
   force sum matches `force.dat` to 12 significant figures, §6.19; **I3** — all six decks
   mesh, counts reproduce §6.16 exactly, §6.21. None of the three has a `data/vv/` record
   with a four-fold tuple yet, so **they are measurements, not records**, and the pre-flight
   must re-run them into `data/vv/` before ADR-039 cites any of their numbers.

   **I7 is still the first thing to run and still decides the campaign** — the measured
   max-Courant fixes `dt`, and `dt` fixes B2, the ladder and the waves. Everything needed to
   run it now exists: the decks write, they mesh, and `moveDynamicMesh`/`pimpleFoam` can be
   pointed at them.

7. **The adversarial review RAN, partially — and the two named blind spots are still
   unreviewed.** 25 of 79 agents completed before the run hit a usage limit. Of six lenses,
   `limit-cycle` and `alignment-ccxdat` completed with their refuter panels; **`template-numerics`
   and `calculix-clauses` — precisely the two places this item said a defect would be invisible
   — lost every refuter**, and `fluid-deck` lost its finder. The synthesis stage never ran.

   What it produced is worth having: 24 candidates, and one defect confirmed by six independent
   refuter votes across two lenses (§6.23), fixed at `8813bdd` before its first caller existed.

   **Still to review, and the reason it matters has not changed:**
   - `template.py` — the committed template bytes and `hg2007_expectation()` state the coupling
     numerics TWICE (`_MAX_ITERATIONS`, `_CONVERGENCE_LIMIT`, the `_ACCELERATION_*` set, the
     basis function, both mesh names). Only their AGREEMENT is checked, so if both copies are
     wrong in the same way every assertion passes. Check them against upstream's
     perpendicular-flap bytes, which is where they were transcribed from.
   - `calculix.py:assert_calculix_deck` — its clauses are the only thing between a wrong deck
     and a plausible number. Look for a clause that compares a value against itself, or that is
     skipped when a parsed field is absent.

   Re-running: the workflow script is preserved and resumable —
   `Workflow({scriptPath: .../stage20-session5-adversarial-review-wf_3d8de5fa-a13.js,
   resumeFromRunId: "wf_3d8de5fa-a13"})` replays the completed agents from cache and re-runs
   only the ones that died.

8. ~~**Phase 3D CLI wiring**~~ — **DONE 2026-08-06 at `7f1d584`.** Both provenance faults
   closed: `_CASE_PROVENANCE` overrides stage and solver_version by CASE (a Stage-20 bundle
   said "Nutils 9.2" and stage 19), and `assert_provenance_describes` is called immediately
   after `compute_provenance` with the SIFs derived from the spec. The expectation is resolved
   by name; an authored case gets `None`, because its expectation is derived from its own spec
   and the materializer asserts it inside `write_precice_config` — asserting the same thing
   from two sources is how two copies drift.

9. **ADR-039 — THE NEXT THING, and nothing may run before it.** Not started. Everything it
   needs is now in place and machine-checkable:
   - the ORDERED band registry is `hg2007_flexible_foil.CLAUSE_BANDS`, with `(no band)` as a
     first-class value — so the shape-8 parity test has a real object to compare against, and
     D9/D10 cannot vanish the way ADR-036's did;
   - the gated/reported-only partition is already asserted disjoint and exhaustive by
     `test_the_gated_and_reported_only_sets_are_disjoint_and_exhaustive`, which is shape-7's
     property — the ADR side of it is what is missing;
   - **the binding tests go in `tests/unit/`** (§6.24), beside `test_stage19_gate_block_sync.py`.
     `tests/stage_20` is not in CI, so a parity test there would not run;
   - B2 carries `<<B2-PENDING-I4>>` and a committed pure sizing function. The **`GATED_TIME_WINDOW_S`
     / `GATED_MAX_TIME_S` sentinels are already `None`**, so no configuration can claim the
     gated verdict until the pre-flight fills them — the ordering is structural, not a rule;
   - the band regex must be anchored at exactly two spaces (`^ {2}`), use `[A-Z]\d{1,2}`, be
     NON-greedy, accept fractional percents and `\(no band\)`, and guard one band token per
     line. Do not re-derive ADR-036's four defects; they are measured (§6.13, §8).
   - **ADR-039 must state that the D3/D4 increment has no V&V dashboard row** — it needs both
     arms, so it is composed by the driver, and the registry-driven report cannot see it.

10. **The campaign driver `scripts/stage20_hg2007_flexible_foil.py` does not exist.** It is
   what byte-duplicates ADR-039's gate block into every bundle (the ADR-036 pattern, and the
   thing `test_adr039_gate_block_sync.py` compares against). It also owns the D3/D4 increment,
   because that needs both arms, and the D5/D6/D7 predicate results, because
   `BenchmarkRunner.run` computes status from `metrics()` alone and would otherwise
   under-report the two clauses carrying HG's headline claim.


**Design decisions already taken, do not re-litigate**

- Plunge driven from the **solid's** leading edge (the pitch is not prescribed — it *arises* from
  the flexibility, per the thesis, so prescribing it would model a different experiment).
- CalculiX **3-D slab of `C3D8I`, dof 3 suppressed**, not plane stress (§6.1).
- **Solid geometry is settled**: 30 mm aluminium teardrop (≈9.6 mm max thickness, measured off the
  scale diagram and cross-checked to 1.7 %) + 60 mm steel plate, structural root at `x = 30 mm`
  where the plate is clamped between the two machined LE halves. Recorded in `reference.md`; the
  deck writer's boundary condition goes at the root, not the nose.
- The rigid control is the **same coupled path with a stiffer plate** (`b/c = 4.23e-3`), which HG
  measured — so both ends of the increment carry an experimental anchor.
- Both the **absolute** bands and the **increment** bands sit in the VERDICT line (operator
  decision), knowing ADR-022 makes a NO-GO on the absolute clause a live outcome.
- The paired path must segment on the **prescribed** period, never an FFT-detected one:
  `paired_delta_uncertainty` compares periods at `period_rtol = 1e-9` and would — correctly —
  refuse two independently-detected periods.

**Ledger (carried, not dropped)**: Stage-11 PSS gates share the S3/S5 hole; mesh fallback ladder
into the V&V runner; vertex-manifoldness (bowtie) check; 3D external-geometry mode; fair-test
surrogate speed-up; **the 393² certification rung (Stage 16, still untouched)**; `vv-transonic.yml`
lacks both a concurrency group and `AERO_RUN_LONG_REAP`; the README STATUS generator cannot express
"complete, not yet tagged"; `select_fluid_mesh` hard-codes `fluid-openfoam` instead of using
`spec.fluid_participant_dir`.

**STAGE-21 prompt**: not yet authored — Stage 20 is not finished, and the next session resumes
Stage 20 rather than starting 21.

## 8. Pointers for next session

- **Read first:** this file (especially §2's session-4 operator decisions and §6.14-§6.16), then
  `docs/handoff-bundle/STAGE-20-RESUME.md`, then ADR-038, then
  `data/references/fsi/heathcote_gursul_2007/reference.md` (§6.2's traps are live). Session 4's
  roadmap, with the four operator decisions folded in, is
  `/root/.claude/plans/stage-20-flexible-refactored-aurora.md`; it carries a commit-by-commit
  sequence for the rest of Phases 3B-4 and a costed pre-flight ordering.
- **Do not re-derive:** the `ccx_preCICE` conventions (§6.1 — they came from upstream's bytes), the
  HG geometry and uncertainties (`reference.md`, text-sourced and exact), or the provenance
  decision (ADR-038 records the rejected alternative and why).
- **Run first to verify:** `pytest -q tests/unit tests/stage_20` (**581** pass as of session 5),
  then `python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5` (~35 s end to
  end; re-verified PASS on 2026-08-05 after the host reboot, `stopped_by=all-exited`, both
  participants rc=0, 2790 cells). Note the smoke REFUSES a dirty tree — that is the provenance
  gate, not a fault; commit first.
- **Do NOT re-derive:** the ADR-036 band-regex defects. Measured this session, and the
  work-of-record had them wrong: `r"^\s+(D\d) [^\n]*within (\d+) %"` **silently DROPS** `D9` and
  `D10` (it needs a literal space after the id, so `D10 ` never matches), the phantom pair comes
  from `^\s+` matching **five-space continuation lines**, and greedy `[^\n]*` reports the **last**
  band on a line mentioning two. Silent omission is strictly worse than aliasing for a parity test:
  forget `D10` in `metrics()` too and both sides agree. The replacement must anchor at exactly two
  spaces, use `[A-Z]\d{1,2}`, accept fractional percents and `\(no band\)`, be **non-greedy**, and
  guard that no clause line carries two band tokens.
- **Corrections to the resume prompt**, all verified against the code — carry them forward:
  `_write_case` is `PreciceCoupledSolver._write_case` at `solver.py:168-207`, **not** in `case.py`;
  `load()` emits **23** scalars, not 20; the `"tutorial"` literal appears at **7 production + 2
  test** sites, not eight; and the approved-plan path the prompt names
  (`tage-20-flexible-warm-beacon.md`) **does not exist** — the real one is
  `/root/.claude/plans/stage-20-flexible-typed-pinwheel.md`, itself stale on `h`, on the
  plane-stress element choice (superseded by the C3D8I slab) and on its Phase-6 sizing. This
  session's roadmap, with the two operator decisions folded in, is
  `/root/.claude/plans/stage-20-flexible-cryptic-umbrella.md`.

- **Session-5 additions to "do not re-derive":** the CalculiX 20-character field limit and the
  representable-value split it forces (§6.17); the `.dat` four-line record shape and its
  seven-digit time (§6.19); that the coded FO compiles under `setpriv --reuid 1000` and that
  its force sum matches `force.dat` (§6.19); that a 70 k-row `*AMPLITUDE` table is fine
  (§6.18); and the mesh table at `farfield_extent_chords = 20` (§6.21). All five were
  measured on aero-dev, and four of them changed the code.

## 9. Artifacts produced

**Session 6 (2026-08-06): 4 commits, `227ffed`..`21840e0`, suite 581 → 664.** New modules:
`aero/vv/fsi/{hg2007_flexible_foil,hg2007_readout}.py`. Modified: `aero/adapters/precice/`
(`case.py` — `AuthoredSource` carries `fluid`/`solid`, `assert_authored_consistent`,
`assert_wetted_curve_matches`, `spec_config_digest`, `EXCHANGE_DIRECTORY`, the participant/uid
validator; `solver.py` — `_materialize` and `load` both split and dispatched exhaustively,
`_materialize_authored`, `_authored_mutations`, `_provided_mesh`; `calculix.py` — even
`n_through_thickness`, `watch_points`; `logs.py` — `iterations_per_window`/`total_iterations`;
`template.py`, `analysis.py` — the watch-point and signal names), `aero/adapters/openfoam/`
(`force_io.py` — the `repeats` policy, `last_occurrence_mask`, `classify_repeat_cadence`;
`flexible_foil.py` — `read_interface_power`), `aero/vv/alignment.py` (the attestation fix and
the unconditional origin check), `aero/vv/fsi/__init__.py`, `import-platform-only.yml`.
New tests: `tests/stage_20/{_hg2007.py,test_authored_materialization.py,
test_coupled_force_cadence.py,test_hg2007_case.py}` plus additions to `test_alignment.py`.

**Session 5 (2026-08-05): 10 commits, `397af1c`..`b9f317f`, suite 418 → 581.** New modules:
`aero/adapters/precice/{template.py,calculix.py,ccx_dat.py}`,
`aero/adapters/precice/templates/{hg2007-precice-config.xml.in,SHA256SUMS}`,
`aero/adapters/openfoam/{flexible_foil.py,force_io.py}`, `aero/vv/alignment.py`. Modified:
`aero/postprocess/limit_cycle.py` (per-cycle objects + prescribed period),
`aero/adapters/openfoam/{_foam_common.py,solver.py}`, `import-platform-only.yml` (five new
fenced modules). New tests: `tests/stage_20/test_{precice_config_template,calculix_deck,
force_io,ddt_scheme,flexible_foil_deck,limit_cycle_paired_inputs,alignment,ccx_dat}.py` plus
the real-bytes fixture `tests/stage_20/fixtures/ccx_dat/ccx220-node-print-totals.dat`.

Earlier sessions: 7 commits on `stage-20-flexible-flapping-wing-fsi`, PR **#44** (draft, all 10
host-side required checks green). New: ADR-038; `db/migrations/005_container_set.{py,sql}`;
`scripts/stage20_{acquire_perpendicular_flap,calculix_smoke}.py`;
`scripts/grant_aero_build_ssh_to_aero_dev.sh` + its runbook; `tests/stage_20/` (45 tests);
`data/references/fsi/{heathcote_gursul_2007,precice_perpendicular_flap}/`;
`data/vv/stage20_calculix_smoke.json`. Modified: the provenance package, `CoupledCaseSpec`, the
executor and the three adapters' failure paths, `CONSTITUTION.md`.

**Session 9 (2026-08-12): 5 commits, `bc24e08`..`c4069bc`, suite 774 → 789, mypy clean.**
New: `scripts/stage20_numerics_screen.py` (the committed screening harness, with `--prepare`
/ `--run` / `--pair` / `--record`; `--pair` runs two arms CONCURRENTLY, which is the shape a
rank count has to be chosen in), `data/vv/stage20_n4_deforming_screen.json`,
`tests/unit/test_stage20_n4_deforming_screen_record.py` (13 tests). Modified: this handoff
(§6.34-§6.36), `docs/handoff-bundle/STAGE-20-RESUME.md` (§6e + §7). No `aero/` module
changed — the screen composes existing writers and reads through
`solver_log.read_fluid_cost_history`, so nothing in the import fence moved.

**Session 8 (2026-08-11): 7 commits `24efcdc`..`c753321`, suite 726 → 774.** The cost reader
and attribution, the driver's `--collect-cost`, the I10 and N2 records, the `fvSolution`
byte-pin, and `FluidNumericsSpec` on the spec.

**Session 7 (2026-08-10): 8+ commits `b222c18`..(see git log), suite 672 → 726, mypy clean repo-wide.**
New: ADR-039 (+ its correction in `a0312e1`), `scripts/stage20_hg2007_flexible_foil.py`,
`aero/vv/fsi/{hg2007_sizing,preflight}.py`, `aero/adapters/openfoam/solver_log.py`,
`tests/unit/test_adr039_{gate_block_shape,gate_block_sync,sizing_function,
b2_marker_state}.py`, `tests/stage_20/{_settling,test_hg2007_readout_windows,
test_solver_log,test_preflight_helpers,test_template_matches_upstream_bytes}.py`,
six `data/vv/stage20_*.json` records. Modified: `hg2007_readout.py` (gated_means),
`calculix.py` (eight new clauses + parser fixes), `template.py` (watch-point constants),
`local_ssh.py`/`launcher.py`/`solver.py` (the additive detached seam),
`import-platform-only.yml` (three new fenced modules), `test_calculix_deck.py`
(+10 tamper tests). Branch history: e1b35b5 → `docs/atlas-pointer`; f704c38 → `8d59d27`.

## 10. Confidence / risk

**Confident.** The two-container coupling is real and measured, not inferred: 50/50 windows
converged, both participants exited 0, and the tip trace shows a deflection under a fluid force
that grows from zero. The provenance change is strictly additive and its backward compatibility is
pinned by tests that construct pre-Stage-20 JSON. The reference's text-sourced values are quoted,
not read off a plot.

**Not yet established.** Everything Stage 20 is actually *for*. There is no authored case, no
pre-registration, no campaign, and therefore no application-fidelity claim — and none may be made
until ADR-039 exists. The smoke says the plumbing works; it says nothing about Heathcote-Gursul,
and the physics it ran is upstream's flap in a channel.

**The known-hard part is still ahead.** ADR-022 measured the platform's 2-D plunging solve missing
HG's *absolute* rigid thrust by −28 %/+58 % with an St-dependent slope error. Stage 20 removes one
of its two root causes (the teardrop-vs-NACA-0012 geometry substitution) but not the other
(2-D vs 3-D). With the absolute clause gated by operator decision, a NO-GO on it is a live and
reasonable outcome; the verdict is designed to be reported clause by clause so that "NO-GO on
absolute fidelity, GO on the flexibility increment" reads as the honest result it would be.

**Bus factor.** The single most important fact not derivable from the code is §6.1 — upstream's
CalculiX conventions, learned from bytes rather than documentation. §6.2's two reference traps are
second: a `C_T/St²` axis under a "thrust coefficient" caption has already cost this repo one
wrong reference file.

**Session-7 revision.** *Confident:* the pre-registration machinery is now real — ADR-039
byte-bound and CI-parity-tested, the gated sentinels structurally refusing an unsized
campaign, and the pre-flight's central finding (§6.29) resting on four independent
measurements that agree (window-1 Courant both arms and both dts, the linear dt scaling,
the iterations logs, two rate intervals at different loads). The detached seam is proven
on the cluster end to end. *The honest state of the claim:* Stage 20's application-fidelity
verdict is still unmade, and the pre-registered NUMERICS — fluid dt locked to the coupling
window on this rung family — cannot reach it on this hardware. That is a finding about the
configuration, not about the physics; the reference, the case, the gates and the driver all
stand, and ADR-040 re-registers only the numerics with the full evidence trail in hand.
*Risk:* the ~3.8 s/coupling-iteration cost decomposition is hypothesis-ranked, not measured
— if the dominant term is PIMPLE itself rather than overhead, subcycling alone buys less
than the arithmetic suggests, and parallel-fluid becomes the load-bearing option.

**Session-9 revision.** *Confident:* the two knobs the operator flagged are now measured
rather than argued, on a harness that re-derives N2's control to four significant figures
before it measures anything new, and both are dead — with the refutation holding a fortiori,
since the screen deformed the mesh 167x further than the campaign ever did and still missed.
The rank count is measured in the shape it gets used in. The candidate stack's ratio survives
the moving mesh and is *better* cold-started than warm, so the budget projection is
conservative. *Corrected:* §6.31's attribution of the 3x to the deforming mesh was wrong, and
the correction lives in a new record rather than an edit to the committed one. *Newly known
and load-bearing:* `--collect` -> `read_arm` has never run on a real coupled run and would
raise on both surviving I4 arms; the fluid function objects stamp the window START and
CalculiX the window END, so a one-window phase offset sits under D10 and P2/P3. That is a
silent-wrong-number defect discovered before it could cost a campaign rather than after.
*Still not established:* everything the stage is for. ADR-040 does not exist, no coupled
confirmation has run, the ceiling decision is unmade, and no gated claim may be made.
*Risk:* the residual factor is attributed to the implicit coupling's permanent cold start on
four consistent signatures but is NOT confirmed — a fluid-only screen structurally cannot
test it, and the probe that would lives in ADR-039 C1, which is frozen and carried over.
