---
stage: 19
stage_name: "Stage 19 — preCICE FSI Core (Turek-Hron FSI3)"
status: complete
date_started: 2026-07-27
date_completed: 2026-07-28
session_duration_hours: 11
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5[1m]
git_sha_start: 30b1adde7e4d60edcb561d18a71acdf3e994b276
git_sha_end: 2a5bbd63a66fddd8c0a4e64f1176aad19023ce83
stage_tag: v0.0.19
next_stage: 20
next_stage_name: "Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul)"
---

# Stage 19 — preCICE FSI Core (Turek-Hron FSI3) — DONE 2026-07-28

> **Read this first. Verdict: GO.** The Turek-Hron FSI3 coupling verification passed
> every pre-registered band, on the full 8000-window run, from a clean tree with four-fold
> provenance. **ADR-016 moves to `accepted`.** What that establishes is *coupling
> correctness* — not application fidelity for a flexible wing, which is Stage 20's separate
> claim with a different solid solver and a different reference.

## 0. The one-paragraph version

`aero/adapters/precice/` exists and works: a real OpenFOAM↔Nutils Turek-Hron FSI3
coupling runs on aero-dev through the platform's own plumbing, with the adapter loaded,
preCICE 3.4.1 configured, interface data exchanged and every time window converging.
Getting there required diagnosing a long-standing infrastructure limit
(**"MPI is blocked in the aero LXCs" is actually an AppArmor rule**) and eight distinct
defects, four of mine and four environmental. An adversarial review then found **13 more,
one of them a hole in the gate's own periodic-steady-state check that would have passed a
diverging solve as GO**. All are fixed. The campaign then ran 8000 coupled windows in
20.30 h and **passed all five displacement bands** — transverse amplitude +2.49 % against
a 15 % band, fundamental frequency +0.90 % against 5 % — with every window converged and
zero non-converged. ADR-016 is `accepted`.

## 1. Deliverables status

| # | Deliverable (verbatim from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `aero/adapters/precice/` populated + `aero[precice]` extra; pins confirmed in an ADR; SIF/container strategy ADR'd | ✅ | 11 modules; ADR-035; one combined `precice-fsi.sif`, built, signed, digest recorded |
| 2 | Turek-Hron FSI3 coupling verification, pre-registered tolerances, `aero/vv/fsi/` + registry + CLI | ✅ | **GO** — all five D-bands passed on the full 8000-window run; gate + pre-registration (ADR-036) committed *before* any run. Bundle: `data/vv/stage19_turek_hron_fsi3.json` |
| 3 | CalculiX SIF built + non-gated smoke | ⚠️ | **SIF built**, signed, digest `4ca47da…` recorded; `ccx_preCICE` links against libprecice. The non-gated perpendicular-flap smoke is deferred to Stage 20 — see §7 |
| 4 | FSI3 reference data DVC-tracked, `reference.md` extended | ✅ | `ref_fsi3.point` + the pinned tutorial archive DVC-tracked; `reference.md` extended *and corrected* |
| 5 | ADR-016 → accepted on gate pass; ADRs; GO/NO-GO; handoff; STAGE-20 prompt; tag | ✅ | **ADR-016 → `accepted`** with a validation record; ADR-035/036 + the ADR-019 amendment landed; verdict GO; STAGE-20 prompt landed; tagged `v0.0.19` |

## 2. Decisions made

- **The `Solver` ABC is not amended** (ADR-035). A coupled run fits `prepare→mesh→run→load`
  once the `CaseDir` is the tutorial root; the Stage-07 promotions (`cd`/`cl` optional,
  `scalars` present) are what make it fit. Same reasoning ADR-008 used for JAX-Fluids.
  Rejected: widening `Solver`/`SolverProtocol`, and widening `Executor` for non-blocking
  submission — both would push cost onto four adapters that gain nothing.
- **Concurrency without touching `Executor`.** The *payload* is made concurrent instead: a
  generated supervisor script backgrounds both participants, takes the coupling down if
  one dies, enforces the ceiling, and always writes `coupled-status.json`. Budget
  exhaustion becomes a *recorded outcome* rather than an inference from a truncated log.
- **One combined SIF for the gated run.** Keeps `container_sif_sha256` single-valued
  without changing `ProvenanceTuple`, the most widely consumed model in the repo. A
  validator refuses a multi-SIF *gated* case structurally. Rejected: two SIFs plus a
  provenance schema change, for one stage.
- **Pins taken from upstream's own attested `reference_versions.yaml`**, not from
  judgement. That settled the openfoam-adapter question with evidence: the last tagged
  release predates OpenFOAM v2412, so a tag would not have built.
- **The reference of record is recomputed, not transcribed** (ADR-036 R3), by the *same
  function* that measures a solve. Not ceremony: the same data yields a uy mean of
  9.66e-4 or 1.47e-3 depending only on the segmentation period.
- **Participants run unprivileged** rather than rewriting the tutorial's inlet. M1's
  declared fallback (`exprFixedValue`) would have worked, but it edits an upstream case
  file, and byte-identity *is* the externality claim.

## 3. Deviations from the stage plan

## 3a. The result (gate D, ADR-036)

Run `turek_hron_fsi3-20260727-152140`: upstream mesh (20 969 cells), `max-time = 8.0 s`,
8000 coupled windows in **20.30 h**, both participants exited 0.

| gate | quantity | measured | reference | error | band | |
|---|---|---|---|---|---|---|
| D1 | transverse amplitude | 3.408544e-2 m | 3.495533e-2 | +2.49 % | 15 % | PASS |
| D2 | fundamental frequency | 5.490204 Hz | 5.539872 | +0.90 % | 5 % | PASS |
| D3 | streamwise amplitude | 2.827944e-3 m | 2.700146e-3 | +4.73 % | 25 % | PASS |
| D4 | streamwise mean | −2.727524e-3 m | −2.856809e-3 | +4.53 % | 25 % | PASS |
| D5 | streamwise frequency | 10.94931 Hz | 11.07420 | +1.13 % | 5 % | PASS |

Diagnostic (never gated): transverse mean 1.644498e-3 m. **K1**: 8000/8000 windows
converged, mean 5.40 iterations against a cap of 100, zero non-converged. **S3**: 19
settled cycles after the 4.0 s discard. **P3**: clean-tree four-fold provenance
(`git_sha 2a5bbd63`, container `ce795873…`).

Worth noting against the pre-registration's own honesty clause: D1 came in at +2.49 %
against a 15 % band. The operator chose 15 % before the reference's own 2.1 % level-to-level
spread was measured, and ADR-036 records that 10 % would also have been defensible. At
+2.49 % the result would have passed either band, so the choice did not decide the outcome —
but that is luck, not method, and a future stage should size the band from the reference's
measured spread rather than from judgement.

## 3. Deviations from the stage plan

- **Timing: the budget call nearly went the wrong way.** Gate I4's measurement is what
  established feasibility. The *transient-inclusive* rate over the first windows is
  ~49-87 s/window, which projects 108 h for `max-time = 8 s` and would have justified
  declaring a budget NO-GO on the spot. But coupling iterations fall steeply as the
  start-up transient clears — 16, 23, 12, 11, 8, 8, 6, 6 … settling at 3 — and the
  completed 200-window calibration measured **13.35 s/window**. The campaign then actually
  ran at **9.1 s/window** average (20.30 h), comfortably inside the 48 h ceiling.
  **This is exactly why ADR-036 I4 requires the measurement before any budget or rung
  decision:** deciding from the early rate would have retired the stage as an
  infrastructure failure.
- **The pre-registration was amended after it was committed.** ADR-036 landed at
  `208cad7`; the adversarial review then found the S3 hole and nine other defects, and
  ADR-036 gained S5 plus tightened C1/K1/K2/I4/P3 wording at `b136858`. This is legitimate
  *only* because no campaign had run and every change makes the gate harder to pass — the
  D bands are untouched. Had a campaign already run, the correct move would have been a
  new ADR and a re-run, as Stage 18 did.
- **CalculiX SIF built; its smoke deferred.** `calculix-precice.sif` is built, signed and
  digest-recorded, and `ccx_preCICE` links against libprecice. The non-gated
  perpendicular-flap coupled smoke was not run — it is inherently two-container, which is
  the multi-container provenance question Stage 20 has to decide anyway, so it belongs
  there rather than being rushed here.
- **The refined-mesh diagnostic (B3) was not run.** Pre-registered non-gated from the
  start, so it bears no verdict and its absence changes nothing about the GO. It is a
  ~20 h run; launch it when the box is free.

## 4. Environment / dependency / schema changes

- `aero[precice]` = `pyprecice==3.4.0` (exact; ABI must match the SIF's preCICE 3.4.1).
  Nothing host-side imports it — see the pyproject comment and ADR-035.
- New pytest marker `stage_19`; new test dirs `tests/stage_19/`.
- New module `aero/postprocess/limit_cycle.py` (additive to ADR-019).
- `containers/precice-fsi.sif` — sha256
  `ce7958737247ae5226d523818e32025b602007c92122a7540205b5dfaf44f7c8`, signed, in
  `SHA256SUMS`. Retires the reserved name `precice-distribution.sif`.
- `containers/calculix-precice.sif` — sha256
  `4ca47da2961d8d6a6033fb216a542165b04419e2527d5d5b8c94cd2771d28668`, signed;
  calculix-adapter commit `51cf777`, CalculiX 2.20.
- `aero/postprocess/cycle_detection.py` gains an opt-in cumulative (linear-trend) drift
  bound + reported fields — the ADR-019 amendment. Default off, so Stage-11 behaviour is
  byte-identical.
- DVC: `ref_fsi3.point` (1.1 MB) and `precice-tutorials-turek-hron-fsi3.tar.gz` (76 KB),
  both pushed to `aero-minio`.
- **aero-dev system change:** `/etc/apparmor.d/local/apptainer` now permits inet/inet6
  stream and dgram sockets. See `docs/operator/apptainer-inet-sockets.md`, including the
  revert command. Applied to **aero-dev only**.

## 5. CI/CD changes

- `import-platform-only.yml`: `aero.adapters.precice` and `aero.vv.fsi` added to the
  import loop; `precice`, `pyprecice`, `nutils` added to the banned tuple.
- No new required checks. `vv-required`'s internal paths-filter already covers
  `aero/adapters/**` and `aero/vv/**`; nothing needed adding, and the workflow itself must
  never be `paths:`-filtered.
- New unit tests run in the existing required `pytest unit` job (287 pass).
- **`README.md`'s STATUS block now reads "Latest tag: v0.0.19".** That tag does **not**
  exist and must not be pushed until a verdict does. The block is generated from this
  handoff's `stage_tag` frontmatter and hand-editing it fails CI; the generator has no way
  to express "intended tag". `status: complete` above is authoritative.

## 6. Gotchas discovered

**Infrastructure**

1. **"MPI is blocked in the aero LXCs" is an AppArmor rule, not an LXC limit.** Ubuntu
   24.04's stub `/etc/apparmor.d/apptainer` profile lists no `network` rules, so AF_INET
   socket creation is denied inside *every* Apptainer container — `su2-v8.sif` too.
   `flags=(unconfined)` does not exempt it; seccomp allows `socket`. Runbook:
   `docs/operator/apptainer-inet-sockets.md`.
2. **buildah cannot run on aero-build.** Unprivileged LXC → a nested userns cannot map the
   subuid range → `newuidmap` is setuid but writing `gid_map` returns EPERM → single-mapping
   fallback → slirp4netns never comes up → every pull fails on DNS while `curl` works.
   `BUILDAH_ISOLATION=chroot` and `GODEBUG=netdns=cgo` do not help. Container builds run on
   the Proxmox host (split-host pattern, Stage-07 precedent). Base images must be
   fully-qualified: the host's `registries.conf` defines no unqualified-search registries.
3. **OpenFOAM refuses `codedFixedValue` as root, unconditionally.**
   `dynamicCode::checkSecurity`'s `isAdministrator()` check in v2412 is not gated by
   `allowSystemOperations` (already 1 in the image), and neither
   `FOAM_ALLOW_SYSTEM_OPERATIONS` nor a user controlDict InfoSwitch changes it. Participants
   drop to uid 1000 via `setpriv`; the case is chowned *after* digest verification.

**Formats and APIs**

4. `xml.etree.ElementTree` and `minidom` **refuse** a preCICE config: `data:vector`,
   `m2n:sockets` etc. use undeclared XML prefixes and CPython always drives expat with
   namespace processing on. Drive `xml.parsers.expat` directly with namespaces off.
5. preCICE's `TXTTableWriter`: header line has a **leading two-space delimiter** and no
   comment marker; rows are newline-**prefixed**, so there is no trailing newline and a
   live file's last row can be partial. A 2-D vector column is `name0  name1`.
6. `blockMesh` prints **`nCells:`**; `cells:` is checkMesh's wording.
7. `precice-config-validate` takes a FILE — `--help` is parsed as the filename, exit 2.
8. gmsh's Python module **dlopens `libGL.so.1` at import**; `libglu1-mesa` is not enough.
9. A `K=V` prefix in a compound shell command binds only to the next command. Passing
   participant env via `build_apptainer_exec(env=...)` put it on the adapter's own `cd`.
10. Upstream's `run.sh` scripts source `../../tools/…`, i.e. **outside** the case
    directory: the bind mount must be the tutorial root, not the case.
11. The openfoam-adapter must be built into `$FOAM_LIBBIN`, and participants run with
    `--no-home`, or the host `$HOME` shadows it via `$FOAM_USER_LIBBIN` — failing only at
    run time.
12. `buildah run` needs a working *container*, not an image.

**Corrections to the inherited record**

13. The upstream `reference-results/` tarballs are **not** a displacement reference — they
    hold 1–3 coupled time windows of `.vtu` exports (preCICE's CI fixture). Both the
    STAGE-19 prompt and Stage-18's `reference.md` implied otherwise; `reference.md` is
    corrected. Side effect: **git-lfs is not needed** — `media.githubusercontent.com`
    serves LFS content over plain HTTPS.

**The review's headline finding**

14. **The periodic-steady-state gate had a hole, in its own machinery.**
    `detect_cycle_convergence` compares *adjacent* cycles only, so a record growing 1.2 %
    per cycle satisfied it without bound while its amplitude grew 30 % across the analysis
    window — and then passed all five displacement bands, producing a GO on a solve that
    never converged, with B4 unable to fire. That is what a slowly saturating added-mass
    instability looks like, i.e. the realistic FSI3 failure mode. Fixed by ADR-036 S5, a
    cumulative first-to-last bound. **`aero/postprocess/cycle_detection.py` also backs the
    Stage-11 moving-mesh PSS gates, which have the same hole — not changed here, because
    that would retroactively alter earlier verdicts. Ledgered.**

## 7. Open items for the next stage (and beyond)

**For Stage 20**

1. **Run the CalculiX perpendicular-flap smoke.** The SIF is built and ready. It is
   inherently two-container, which forces the multi-container provenance decision Stage 20
   has to make anyway (`ProvenanceTuple` carries one `container_sif_sha256`; the gated-run
   validator refuses a multi-SIF *gated* case by construction). Decide that deliberately —
   extend the tuple with its own ADR, or keep the claim non-gated — rather than working
   around the validator.
2. **Do not reuse this stage's result as Stage-20 evidence.** FSI3 establishes coupling
   correctness with a Nutils solid. A flexible wing with a CalculiX shell model against
   Heathcote-Gursul is a different claim with a different reference. ADR-016 exists to keep
   them apart.
3. **Optional, cheap, and now unblocked:** the refined-mesh (38 k) diagnostic, pre-registered
   non-gated in ADR-036 B3. ~20 h. It would give grid sensitivity on a result that currently
   rests on one rung.

**Ledger (new this stage)**

4. **Stage-11 PSS gates share the S3 hole** (item 6.14). Decide deliberately whether to
   backfill the cumulative bound there and re-run, or to record the exposure.
5. The `precice` extra is exercised only inside the SIF; if a host-side participant ever
   lands, revisit.
6. `_txt_table` treats any short final row as a partial write; a file truncated
   mid-campaign by something else would read as one dropped row.
7. The `README` STATUS generator cannot express "stage complete, not yet tagged" — see §5.
   Worth a small fix before a future partial stage repeats it.

**Ledger (carried, not dropped)**: mesh fallback ladder into the V&V runner;
vertex-manifoldness (bowtie) check; 3D external-geometry mode + generic external-aero
autogen; fair-test surrogate speed-up; **the 393² certification rung (Stage 16, still
untouched)**.

**STAGE-20 prompt exists**: `docs/handoff-bundle/STAGE-20-flexible-flapping-wing-fsi.md`.

## 8. Pointers for next session

- **Read first:** ADR-036 (the gate block), then `docs/operator/apptainer-inet-sockets.md`,
  then §6 above. The gate block's operational copy is
  `scripts/stage19_turek_hron_fsi3.py::PREREGISTERED_GATE_BLOCK`, byte-identical by CI.
- **Do not re-derive:** the pins (ADR-035 §Decision outcome), the reference identification
  (`reference.md` §"Which row it is"), or why buildah runs on the host.
- **Run first to verify:** `pytest -q tests/unit` (285 pass), then
  `python scripts/stage19_turek_hron_fsi3.py --preflight --timeout 3600`. I1 and I3 pass
  today; I4 is the open measurement.

## 9. Artifacts produced

13 commits on `stage-19-precice-fsi-core`. New: `aero/adapters/precice/` (11 modules),
`aero/postprocess/limit_cycle.py`, `aero/vv/fsi/`, `scripts/stage19_{acquire_fsi_reference,
turek_hron_fsi3}.py`, `scripts/build_{precice_fsi,calculix}_sif.sh`,
`containers/precice-fsi.{Dockerfile,def}`, `containers/calculix-precice.{Dockerfile,def}`,
ADR-035, ADR-036, the STAGE-20 prompt, the AppArmor runbook, and the FSI3 reference set.
`precice-fsi.sif` is built, signed and published.

## 10. Confidence / risk

**Confident.** The coupling is real: participants exchange data, the adapter loads, every
time window converged, and the watch-point is written. The pins are upstream's own
attested set. The reference is identified with evidence (L4 at 0.77 % vs 2.39 %/4.05 %)
and recomputed by the same code that will measure the solve. The pre-registration is
mechanically bound to the code in required CI, and the band-parity and gate-block checks
were mutation-tested.

**Settled by measurement.** The coupling is correct within the pre-registered bands, and
the run converged in all 8000 windows at a mean of 5.40 iterations against a cap of 100 —
FSI3's added mass, the thing that makes it the benchmark's hardest case, never destabilised
it. Throughput is a solved question: 9.1 s/window, 20.30 h.

**Still not certain.** The result rests on **one mesh rung**; the refined-mesh diagnostic
was not run, so there is no grid-sensitivity evidence behind the numbers. The bands are
engineering judgement anchored to the reference's discretisation spread, not a
platform-owned convergence study — no GCI is claimed and the tier is `validated`, not
thesis-grade. D5 is correlated with D2 and is labelled as such rather than counted as
independent. And the whole claim is coupling correctness with a Nutils solid; nothing here
speaks to a CalculiX shell model.

**Bus factor.** The AppArmor change is the single most important fact not derivable from
the code; it is in a runbook for that reason. The second is that `gated` is *derived* from
the rung and end time, so a diagnostic run cannot accidentally carry a pre-registered
verdict — if that derivation is loosened, ADR-036 B3's declaration becomes decorative.

**Bus factor.** The AppArmor change is the single most important undocumented-elsewhere
fact; it is in a runbook rather than only in this handoff for that reason. The other
sharp edge is that `gated` is *derived*, so a future caller cannot accidentally attach a
pre-registered verdict to a diagnostic run — if that derivation is ever loosened, the B3
declaration becomes decorative.
