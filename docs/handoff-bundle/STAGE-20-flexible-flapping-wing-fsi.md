# STAGE 20 — Flexible Flapping Wing FSI (Heathcote-Gursul) — flagship capstone

> Stage 19 built the partitioned-coupling machinery and verified it on the supported
> upstream Turek-Hron FSI3 tutorial (OpenFOAM fluid + Nutils solid). Stage 20 turns that
> machinery on the **mission**: a flexible flapping foil, validated against *experimental*
> data. This is the capstone forward capability — the last physics stage before v0.1.0 —
> and it is the first FSI claim the platform makes about its own application rather than
> about a benchmark.
>
> **The two claims stay separate (ADR-016).** Stage 19's evidence is *coupling
> correctness*, on a benchmark with a Nutils solid. Stage 20's evidence is *application
> fidelity*, with a CalculiX solid and shell/membrane elements that Nutils does not
> provide. Neither substitutes for the other, and the handoff must not let them blur.

## BEFORE YOU START — READ

1. `CLAUDE.md`; `.aero-stage` (→ `20`); `docs/handoffs/STAGE-19-*-DONE-*.md` — especially
   §6 (gotchas) and §7 (open items). The Stage-19 verdict determines what you inherit:
   if it was a GO, coupling correctness is established and you build on it; if it was a
   NO-GO on budget, the machinery exists but the coupling claim does not, and Stage 20
   must say so in every result it reports.
2. **ADR-016** (the split-solver strategy — Stage 20 is its second half), **ADR-035**
   (adapter shape, pins, container strategy), **ADR-036** (the pre-registration pattern
   you will mirror). ADR-024 (flapping kinematics), ADR-018/019 (mesh motion, unsteady
   post-processing), ADR-023/029 (paired-difference and independent-RSS delta U95).
3. `.claude/rules/flapping-validation-ladder.md` — Stage 20 fills the **flexible**
   flapping row, and Hard Rule 15 requires an experiment-anchored gate.
4. `docs/vv/output-validity-bar.md` and `aero/vv/reportable.py` — this stage is expected
   to produce a **thesis-grade `ReportableResult`**, which means a full U95 envelope, not
   just a tolerance comparison.

## Why this stage

Flexible flapping is the flagship demonstration domain, and flexibility is not a detail:
Heathcote & Gursul (2007) show that chordwise flexibility *changes the sign of the
conclusion* — a moderately flexible foil produces more thrust and higher propulsive
efficiency than a rigid one over a range of Strouhal numbers. A platform that optimises
flapping wings without being able to model that is optimising the wrong problem.

## Deliverables

1. **CalculiX in the loop.** `calculix-precice.sif` exists from Stage 19 (digest in
   `containers/SHA256SUMS`); Stage 20 makes it a *participant*. Extend
   `aero/adapters/precice/` with the CalculiX solid path: the `.inp` deck writer (typed,
   fail-loud, `aero/`-core-clean), the adapter's `config.yml`, and the shell/membrane
   element choice. This is a **multi-container** coupled run, so it uses
   `CoupledCaseSpec(gated=...)` honestly — see deliverable 5 on provenance.
2. **The Heathcote-Gursul case** in `aero/vv/fsi/`: a plunging flexible foil (NACA 0012
   teardrop / flat plate with a chordwise-flexible trailing section), matched to the
   published Re, Strouhal range and stiffness ratios. Reference data DVC-tracked under
   `data/references/fsi/heathcote_gursul_2007/` with the Stage-18/19 acquisition
   discipline: `reference.md` carrying citation, licence, digitization method and the
   digitization uncertainty that must flow into `u95_input`. **Digitized points carry
   real uncertainty — do not record them as exact.**
3. **Pre-registered gate block** (ADR-037+) committed BEFORE any campaign run, mirroring
   ADR-036: pins, configuration integrity, pre-flight, reference integrity, coupling
   convergence, periodic steady state, and the bands. Gate on **thrust coefficient and
   propulsive efficiency vs the published flexible-foil data**, with the rigid case as the
   matched control. Reuse `aero.postprocess.analyse_limit_cycle` so the reference and the
   measurement are extracted by the same code (the Stage-19 discipline).
4. **The flexible-vs-rigid delta, done properly.** This is the mission-shaped claim:
   flexible and rigid at *matched numerics and mesh topology* so correlated errors cancel,
   with `u95_delta` composed via `compose_improvement()` from the paired-difference
   estimator (ADR-023) — **not** hand-entered. Hard Rule 12: the delta is only
   thesis-grade if it exceeds k·U95 with k = 2.
5. **Provenance for a genuinely two-container run.** Stage 19 kept the gated run
   single-container so `container_sif_sha256` stayed single-valued, and
   `CoupledCaseSpec._single_container_for_gated_runs` enforces that structurally. Stage 20
   cannot: OpenFOAM and CalculiX are two images. **Decide this deliberately and record it
   in an ADR** — either extend `ProvenanceTuple` to carry a composite/multi-digest
   container field (a change to the most widely consumed model in the repo, so it needs
   its own justification), or define a reproducible composite digest. Do not work around
   the validator; change the contract on purpose or keep the claim non-gated.
6. ADR(s); GO/NO-GO; post-stage handoff; tag `v0.0.20`. If Stage 20 closes GO, the
   platform is at the v0.1.0 checkpoint described in `README-handoff.md` — say so
   explicitly in the handoff rather than leaving it to be inferred.

## GO / NO-GO

**GO** = the flexible-foil case runs end-to-end through the platform's plumbing with
four-fold provenance; thrust and propulsive efficiency fall within the pre-registered
bands of the published Heathcote-Gursul values; and the flexible-vs-rigid delta is
reported with a composed U95 envelope. **NO-GO** = it runs but misses the bands, or cannot
run within budget: ship the CalculiX participant, the case, the harness and the loud gate,
and record honestly what is missing. **Never relax a band.**

## Infra + conventions + inherited notes

- Serial-only aero-dev (MPI blocked); coupled participants launch concurrently under
  `aero.adapters.precice.launcher`'s supervisor, which records `stopped_by` so a budget
  ceiling is a *recorded outcome* rather than an inference. Budget tier for this stage is
  **burst** ($1-2k) per `README-handoff.md` — that is per-campaign-approved and must be
  requested explicitly, not assumed.
- **Inherited gotchas from Stage 19** (all in its handoff §6): the adapter must be built
  into `$FOAM_LIBBIN` and participants run with `--no-home`, or the adapter library is
  shadowed by the host `$HOME` and fails only at run time; gmsh's Python module dlopens
  `libGL.so.1` at import; a `K=V` prefix in a compound shell command binds only to the
  next command, not the participant; buildah cannot run on aero-build (unprivileged LXC,
  nested userns cannot map subuids) so container builds run on the Proxmox host;
  `precice-config-validate` takes a FILE, not `--help`.
- **Do not reuse Stage 19's numbers as evidence for Stage 20.** Different solid solver,
  different physics, different reference. ADR-016's whole point is that these are separate
  claims.
- Ledger items carried (do not silently drop): promote the mesh fallback ladder into the
  V&V runner; vertex-manifoldness (bowtie) check in `aero/geometry`; 3D external-geometry
  mode + generic external-aero autogen; fair-test surrogate speed-up; **the 393²
  certification rung (Stage 16, still open and untouched)**; and anything Stage 19's
  handoff §7 adds.
- Conventional commits `<type>(stage-20)`; branch + PR; `.venv/bin` on PATH for pre-commit,
  and **verify every commit with `git log`** — the ruff-format hook can exit 0 having
  rolled the commit back.

## POST-STAGE HANDOFF (mandatory)

`docs/handoffs/STAGE-20-*-DONE-*.md` (frontmatter + 10 sections). Emphasize: the
flexible-vs-rigid delta and its U95 envelope; the application-fidelity result against
Heathcote-Gursul and how it differs in kind from Stage 19's coupling-correctness result;
the provenance decision for multi-container runs; and what v0.1.0 still needs. Confirm the
next stage's prompt exists. Tag `v0.0.20`.
