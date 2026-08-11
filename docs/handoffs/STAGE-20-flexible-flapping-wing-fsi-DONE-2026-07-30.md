---
stage: 20
stage_name: "Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul)"
status: partial
date_started: 2026-07-30
date_completed: 2026-08-10
session_duration_hours: 19
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5[1m]
git_sha_start: 42ebb55e984f6762e982d358678c443c857b6dce
git_sha_end: 3a7491deed7a0d955940abc3c61bc851d22a028c
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

## 7. Open items for the next stage (and beyond)

**SESSION-9 RESUMPTION PATH (supersedes everything below).** Session 8 closed the
measurement task; `docs/handoff-bundle/STAGE-20-RESUME.md` §6d + §7 is the map, and
§6.31-§6.33 above are the evidence. In one line: **two of the three named levers are
refuted by a measured bound, the cost is the pressure solve, the combined lever is 8.04x,
and the 14-day ceiling is out of reach at any settled-cycle count.**

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
