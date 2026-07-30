# ADR-038 — Multi-container provenance: a container roster, not a composite digest

- **Status:** proposed
- **Date:** 2026-07-30
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 20)
- **Stage:** 20
- **Supersedes:** none (resolves the followup ADR-035 §"If a future gated run genuinely needs two
  containers" deliberately left open)

## Context and problem statement

Stage 20's flexible flapping-wing FSI case runs **two containers**: the OpenFOAM fluid participant
out of `precice-fsi.sif` and the CalculiX solid participant out of `calculix-precice.sif`. The
four-fold provenance contract (ADR-004, CONSTITUTION Invariant 3) carries exactly one
`container_sif_sha256`, so no honest four-tuple can describe such a run.

Stage 19 handled this by **refusing** it: `CoupledCaseSpec._single_container_for_gated_runs` raised
unless a gated case used a single SIF, and the CalculiX smoke was therefore declared `gated=False`
with the second SIF's *name* riding inside `config_hash`. That was correct for Stage 19, whose gated
claim genuinely was single-container, and ADR-035 recorded the deferral explicitly: *"If a future
gated run genuinely needs two containers, `ProvenanceTuple` needs a decision of its own; this ADR
deliberately does not pre-empt it."*

Stage 20 is that future. Its gated claim — application fidelity for a flexible flapping wing — is
**intrinsically** two-container, because the solid solver is the whole point of the claim (ADR-016
chose CalculiX for shell/membrane elements that Nutils does not provide). The options are to change
the contract or to abandon the claim.

Two properties make this harder than a normal schema change:

1. **`ProvenanceTuple` is the most widely consumed model in the repo** — 49 files touch it, plus a
   Postgres mirror table with a positional INSERT, a hard-coded four-key completeness check, and a
   required CI job. It is `frozen=True, extra="forbid"`, so persisted JSON is validated strictly.
2. **The record must stay invertible.** A digest that cannot be resolved back to the exact bytes
   that ran is decoration. Whatever is logged must let a third party — with MLflow alone, or the repo
   alone, or the bundle alone — recover both SIFs.

Note what the Stage-19 arrangement did *not* achieve, since it is the gap this closes:
`config_hash` bound the string `"calculix-precice.sif"`, never the bytes it named. A rebuilt CalculiX
SIF under the same filename would have produced an identical `config_hash`.

## Decision drivers

- **A run's provenance must describe everything that ran.** A tuple naming one of two containers is
  not "mostly complete"; it is wrong, and silently so.
- **Nothing that already works may change behaviour.** Every pre-Stage-20 run, tag set, Postgres row
  and persisted bundle must remain valid and byte-identical, without a migration pass over history.
- **The constraint should be removed, not worked around.** The stage prompt is explicit: *"Do not
  work around the validator; change the contract on purpose or keep the claim non-gated."*
- **Fail loud.** A mis-described multi-container run must fail before it produces numbers, not be
  discovered when someone tries to reproduce it.

## Considered options

1. **A `containers` roster field on `ProvenanceTuple`** — an explicit, ordered list of
   `(name, sha256)` for every participating SIF, empty for single-container runs.
2. **A composite/set digest folded into the existing field** — redefine `container_sif_sha256` as
   the sha256 of a canonical manifest of the participating SIFs, keeping the schema untouched.
3. **Keep multi-container runs non-gated** — carry Stage 19's arrangement forward unchanged.

## Decision outcome

Chose **Option 1** because the record should say what happened rather than encode it: a reader of a
composite digest cannot tell which containers ran without a side table, whereas a roster is
self-describing at every layer it passes through.

The design is **strictly additive**, which is what makes a change to the repo's most-consumed model
affordable:

- **`container_sif_sha256` keeps its exact meaning** — the SIF *of record*, still resolved by
  basename in `containers/SHA256SUMS`. No existing consumer changes behaviour and no historical run's
  tag becomes irreproducible.
- **`containers: tuple[ContainerRef, ...] = ()`** is new and defaults empty. Persisted bundle JSON
  lacks the key and parses via the default; `extra="forbid"` is untouched.
- **`as_mlflow_tags()` adds a fifth key `container_sif_set` only when the roster is non-empty.** The
  four canonical keys keep their shape, so the hard-coded completeness check in
  `aero/provenance/mlflow.py` and every existing dashboard are unaffected, and a single-container
  run's tag set is byte-identical to what it was before Stage 20.
- **Postgres gains a nullable `container_sif_set TEXT`** (migration `005_container_set`), holding
  *exactly* the tag value. Keeping the mirror byte-comparable with the tag is what lets the Stage-04
  completeness check compare them directly instead of parsing either side. `NULL` — not `""` — marks
  a single-container run, so "no roster" and "an empty roster" stay distinguishable in a query.

### The completeness rule, and where it is enforced

Three ways a roster could lie, all refused by a model validator rather than at read time: a
**one-entry** roster (a single-container run wearing multi-container clothes); **duplicate or
unsorted** names (so the recorded order is canonical and two runs of the same set compare equal); and
a roster that **omits the container of record** (the tuple would describe less than what ran).

The blanket refusal in `CoupledCaseSpec` is *replaced, not deleted*. The obligation moves to
`assert_provenance_describes(spec, provenance)`, called immediately after `compute_provenance` and
before anything runs:

- a single-SIF case must carry an **empty** roster;
- a multi-SIF case must carry a roster whose names are **exactly** the participant SIFs.

That check belongs there rather than in the spec validator for a simple reason: a spec knows SIF
*names*, not digests. Stage 19's validator could only ever have enforced a proxy for the property
that actually matters.

### Consequences

**Positive**

- Stage 20's gated claim becomes expressible without weakening it, and `config_hash` stops being
  asked to carry integrity it never had (it bound a filename, not bytes).
- The record is invertible three independent ways: the MLflow `container_sif_set` tag alone; the
  repo's `containers/SHA256SUMS` alone; the campaign bundle alone.
- Every extra SIF is resolved through the same `container_sif_sha256()` lookup, so an unrecorded
  container fails loud exactly as the container of record always has.
- A pre-existing hole closed in passing: `start_provenance_run(extra_tags=…)` could silently
  overwrite a provenance tag, which would have made MLflow and the Postgres mirror describe different
  runs. Collisions now raise.

**Negative (honest limits)**

- `ProvenanceTuple` now has a field most runs never populate. That asymmetry is deliberate — the
  alternative, a one-entry roster on every run, would make every historical record non-uniform for no
  gain — but it is a shape a future reader must understand rather than infer.
- The roster records *which* containers ran, not *which participant used which*. That mapping lives
  in the `CoupledCaseSpec` dump inside `config_hash`'s preimage. Adding it here would duplicate a
  fact the case spec already owns.
- Nothing forces a multi-container run to *use* the roster outside the coupled path;
  `assert_provenance_describes` is a call, not a type. A driver that skips it can still log a
  single-digest tuple for a two-SIF run. Mitigated by making it the documented step in the campaign
  driver and by the gate block's P-family.
- The Postgres change requires the migration to be applied on LXC 202 before the first gated
  multi-container run mirrors a row; until then such a run fails loud at the mirror.

**Neutral / followup**

- **CONSTITUTION Invariant 3 is clarified, not amended in substance.** Its rule — every run logs the
  four tags — is unchanged and still enforced by the same CI job; only item 3's *description* is
  widened to name the container of record and point at the roster. The ≥72 h amendment window applies
  to the wording change; the campaign does not depend on it, because the enforceable rule is
  untouched.
- Ledgered: `provenance-completeness` verifies the four tags are well-formed 64-hex and that the
  Postgres row matches, but does **not** check membership in `containers/SHA256SUMS`. Adding that is
  a strict improvement independent of Stage 20.

## Pros and cons of considered options

**Option 1 — a `containers` roster (chosen)**

- Good: self-describing at every layer; invertible without a side table; strictly additive; the
  completeness rule is expressible as a validator; an unrecorded SIF still fails loud.
- Bad: touches the repo's most-consumed model and its Postgres mirror; a field most runs leave empty.

**Option 2 — a composite/set digest in the existing field**

- Good: no schema change, no migration, no new field; the regex and every consumer are untouched.
- Bad: the logged digest resolves to nothing in `containers/SHA256SUMS`, so inverting it needs a new
  side manifest (`CONTAINER_SETS`) that must itself be kept consistent by yet another CI check — the
  same total surface, arrived at indirectly. Worse, it silently **redefines** the meaning of
  `container_sif_sha256` for a subset of runs while leaving the field name and type identical, so a
  reader cannot tell from the record which meaning applies. Storing a hash of a list where a list
  would do trades legibility for the appearance of not having changed anything.

**Option 3 — keep multi-container runs non-gated**

- Good: zero risk; carries Stage 19's arrangement forward.
- Bad: Stage 20's gated claim is intrinsically two-container, so this abandons the stage's central
  deliverable. Retained only as the declared contingency: if Option 1 is not ratified before the
  campaign, the campaign runs non-gated and the verdict is NO-GO-with-partial-delivery.

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-20-flexible-flapping-wing-fsi.md` (deliverable 5)
- Related ADR: ADR-004 (the four-fold contract), ADR-035 §Followup (the deferral this resolves),
  ADR-016 (why the solid solver is CalculiX and therefore why this is unavoidable)
- Related handoff: `docs/handoffs/STAGE-19-precice-fsi-core-DONE-2026-07-27.md` §7 item 1
- Code: `aero/provenance/four_fold.py`, `aero/provenance/db.py`, `aero/provenance/mlflow.py`,
  `aero/adapters/precice/case.py`, `db/migrations/005_container_set.{py,sql}`,
  `tests/stage_20/test_multi_container_provenance.py`
