# 00-MISSION-AND-SCOPE — the aerodynamic shape optimizer

> **Governing scope document.** Paste this alongside every stage prompt. Where it
> conflicts with the original project brief (`archive/00-CONTEXT-project-brief.md`) or
> any stage prompt, **this file governs.** Adopted and motivated by **ADR-013**
> (optimizer-mission refocus). The capability-layer architecture and the
> verify-every-optimum discipline come from the architecture briefing
> (`docs/architecture/BRIEFING-architecture-review-for-independent-challenge.md`),
> partially adopted per ADR-013.
>
> *History:* this document supersedes an earlier "two-flagship (flapping + riblet)"
> refocus. That framing was wrong — riblets were only ever an example, and the
> optimizer (treated then as backlog) is the actual mission. The superseded version is
> kept at `archive/00-MISSION-AND-SCOPE-original-two-flagship.md` for provenance.

---

## 1. The mission

`aero-research-platform` is a **hypothesis-driven aerodynamic shape/topology
optimizer.** A researcher brings a hypothesis, plugs in geometry (parametric first;
CAD/STL/3MF later), defines an aerodynamic objective, and the platform returns an
**improved, CFD-verified design.** Think *topology optimization, but for aerodynamics*:
an Onshape-like **design-in → improved-design-out** workflow in which **CFD is the
ground truth.**

The deliverable is the optimizer. The forward CFD + UQ + provenance stack is the
**foundation that makes the optimizer's claimed improvements trustworthy** — not the
product in itself. Every reported improvement must clear the same bar: a CFD-verified
performance delta whose magnitude exceeds its own quantified uncertainty.

### Flagship demonstration domain — flapping-wing aerodynamics
Flapping-wing is the **single flagship**, chosen deliberately because it is **broad**
(insect / bird / bat; rigid and flexible; hovering and forward flight; kinematics and
planform) and **underexplored** — which is exactly where a rigorous optimizer can
produce genuinely new, validated answers. Re ≈ 10²–10⁴ for the target regime
(transitional; fully-turbulent RANS is inappropriate — see §3.3), leading-edge-vortex–
dominated lift, prescribed or fluid-structure-coupled (flexible) kinematics, moving and
deforming geometry.

### Riblets / shark-scale — an example, not a flagship
Bio-inspired passive drag reduction (riblets, denticles) is **one illustrative example**
of a problem the platform can host — a narrow, near-wall turbulence effect that is
already well answered in the literature (Bechert 1997; García-Mayoral & Jiménez 2011;
the in-service AeroSHARK film). It is **not** a development priority. The riblet-specific
roadmap (smooth-wall channel DNS, riblet meshing, the Bechert drag-reduction curve) is
**cut**; the supporting commentary is retained only as the demoted example in §A
(appendix). **PyFR / wall-resolved DNS returns to kept-optional** — it was promoted to
core only to serve riblets, and near-wall turbulence is no longer a near-term core
requirement.

**Consequence for every future session:** ask of any proposed work, "does this advance
the optimizer or the flapping-wing flagship, and does it raise the bar on
reproducibility, validation, or the trustworthiness of a reported improvement?" If not,
it is out of scope until that changes (the **SCOPE-GATE** rule — it gates *effort
allocation*, not interface generality).

---

## 2. Re-scoping (relative to the original brief)

The brief described a generic do-everything CFD/ML platform. The optimizer mission
re-weights it sharply. **General architecture is retained** (the `Solver` /
`Surrogate` protocols, the capability layers, the provenance backbone — all
mission-agnostic and correct); **effort is prioritized** around the optimizer and the
flapping flagship.

| Component | Original brief | **Revised** | Why (engineering, not preference) |
|---|---|---|---|
| Four-tuple provenance backbone (DVC/MLflow/Postgres) | Core | **Core — untouched** | Thesis-grade reproducibility underwrites every reported improvement. The strongest part of the build. |
| OpenFOAM-ESI | Core | **Core** | The forward workhorse: moving-mesh flapping (v2412 ships `dynamicMotionSolverFvMesh`/AMI/`overPimpleDyMFoam`) + cheap iteration for the optimization loop. |
| **The optimization loop** (Bayesian-opt → surrogate-accelerated → adjoint/generative) | (absent — was "surrogate zoo") | **Core — the mission** | Design-in → CFD-verified-improved-design-out. A named milestone (§4), not backlog. |
| **Surrogate *framework*** (`Surrogate` ABC, `CertificateOfValidity`) | Core | **Core — repurposed for own-data** | Re-activated to **accelerate the optimizer**, trained only on the platform's own validated CFD (NO foreign data). The framework is verified dataset-agnostic; the automotive specificity was only ever in the loaders. |
| **Arbitrary-geometry ingestion + robust meshing** (STL/CAD/3MF; CadQuery/build123d) | (absent) | **Core — committed milestone** | "Plug in any geometry and optimize it" is the north star; automated meshing on imported geometry is the dominant robustness risk (§3.2). |
| preCICE + CalculiX (FSI) | "nice demo" (Stage 11) | **Core (later)** | Flexible flapping *is* FSI — the flagship capstone forward capability. Coupling verified on the supported Turek-Hron tutorial; CalculiX for the application (ADR-016). |
| **SU2** (already built) | Core | **Frozen-optional — adjoint seed** | Bio flows are low-Mach, so SU2 is not load-bearing for the forward problem — but its discrete adjoint (with DAFoam v5) is the seed of the post-v0.1.0 gradient/topology-optimization layer. Keep what's built. |
| PyFR (high-order, GPU) | Core (riblet driver) | **Frozen-optional** | Promoted only to serve riblets; near-wall DNS is no longer near-term core. Adapter stays, frozen. |
| NekRS | another GPU solver | **Frozen-optional** | Canonical channel DNS; not on the optimizer path. Adapter stays, frozen. |
| JAX-Fluids 2.x (differentiable) | Core | **Frozen-optional** | A differentiable-CFD path for gradient-based optimization *someday*; orthogonal to the near-term loop. Adapter stays, frozen. |
| DoMINO / Transolver / FIGConvNet / X-MGN on DrivAerML | Core (Stages 9–10) | **CUT (as designed)** | Trained on **car shapes** — cross-domain transfer to wings is *unresolved* in the literature (no evidence it helps or hurts), and the own-data surrogate factory sidesteps the question. The DoMINO code + SIF + data are **frozen, not deleted** (ADR-013). |
| Mixture-of-Experts gate | Core | **CUT** | Pure engineering surface; no payoff for the optimizer mission. |
| DPW-7 / HLPW-5 validation | Core (Stage 12) | **CUT** | Transport-aircraft cruise. Replaced by the flapping validation ladder (§4). NASA TMR kept as the general turbulence-model baseline. |
| UQpy / Dakota UQ | Core (Stage 12) | **Core — reframed** | The optimizer's integrity guarantee: a reported improvement's CFD-verified delta must exceed its combined U95. The error bar *is* the result (§3.4). |
| NeMo Agent Toolkit + AI-Q fork | Core (Stage 14) | **Deferred indefinitely** | Scope creep; ahead of its ecosystem. Not on the critical path. |
| Literature miner | Core (Stage 15) | **Deferred indefinitely** | A reference manager suffices for now. |
| Zenodo DOI + CITATION.cff + JOSS | Core | **Keep** | Citability is part of "thesis-grade." Cheap to maintain. |

**Net effect:** the solver fleet narrows to **OpenFOAM (core) + preCICE/CalculiX (FSI,
later)**, with SU2 / PyFR / NekRS / JAX-Fluids **frozen-optional** (kept, not deleted).
The ML half is re-pointed from a fixed automotive zoo to an **own-data surrogate factory
that accelerates the optimizer.** Validation re-aims from cars/transport-aircraft to the
flapping ladder. You lose nothing you'll miss and reclaim most of your time for the
mission.

---

## 3. Requirements the original brief omits (gaps to close)

### 3.1 Moving-mesh / overset for flapping
Prescribed-kinematics flapping needs dynamic/overset mesh. OpenFOAM-ESI **v2412 (already
pinned)** ships `dynamicMotionSolverFvMesh` + solid-body motion functions + AMI sliding
interfaces and the `overPimpleDyMFoam` overset solver — so this is **adapter wiring, not
a tool hunt.** The current OpenFOAM adapter has only a steady-state path; the moving-mesh
path is a prerequisite for any flapping case and must precede flapping V&V. *(Stage 11.)*

### 3.2 Arbitrary-geometry ingestion + robust meshing (the north-star gap)
"Plug in any geometry and optimize it" requires ingesting STL/CAD/3MF and meshing it
reliably. **Automated meshing on never-before-seen, non-watertight, or thin-feature
geometry is the dominant practical failure mode** (snappyHexMesh/gmsh/cfMesh all
struggle). Required: watertightness/quality gating, repair, sandboxing with fallback.
The pragmatic pattern is **optimize in a parametric or FFD/SDF space, then emit
manufacturable CAD** via CadQuery / build123d (both production-ready, OCCT-backed,
2026). *(Stage 17; this replaces the demoted riblet-meshing gap.)*

### 3.3 Transition modeling
Bio Reynolds numbers are **transitional** (laminar separation bubbles, transition on
flapping wings). Fully-turbulent RANS is wrong here. OpenFOAM v2412 ships **γ-Reθ
(Langtry-Menter, `kOmegaSSTLM`)**; published Robofly-replication CFD uses
laminar/incompressible Navier-Stokes for the lowest-Re hovering cases. Add a transition
path and validate it. *(Stage 13.)*

### 3.4 The improvement-exceeds-uncertainty guarantee (UQ as the optimizer's integrity)
The optimizer will claim performance deltas. A claimed improvement smaller than the
solver's own uncertainty is not a result — it is numerical noise. Therefore:
- **Total U95 composes three independent contributions** (root-sum-square):
  `u95_numerical` (discretization — GCI / ASME V&V 20, which covers *only* this),
  `u95_statistical` (the sampling error of a time/phase-average — batch-means /
  autocorrelation effective-sample-size, after a periodic-steady-state cycle-convergence
  check), and `u95_input` (parametric). GCI alone is insufficient for unsteady flows.
- **No reported improvement is thesis-grade unless its CFD-verified delta exceeds k·U95**
  (default k = 2). For an optimization **delta**, run the baseline and the candidate at
  **matched numerics/mesh-topology** so correlated errors cancel — the uncertainty of
  the delta is then far smaller than the RSS of the two absolute uncertainties (the same
  paired-comparison principle the riblet community uses for delta-drag). This is the
  **IMPROVEMENT-EXCEEDS-UNCERTAINTY** invariant.
- **Closed-loop U95-gating is nascent in the literature** — a genuine research
  contribution of this platform, and therefore real custom development, scoped across
  Stages 12 (the U95 machinery) and 15 (first in-loop use), not assumed off-the-shelf.

### 3.5 CFD-verified optima only (guarding the AI-scientist failure modes)
Autonomous optimization/discovery loops have documented failure modes (Luo, Kasirzadeh &
Shah, arXiv:2509.08713): **post-hoc selection bias** (cherry-picking the best of N
candidates), **metric misuse** (reporting a surrogate's optimistic prediction as the
result), and **data leakage**. Mitigation, enforced as a rule: **every reported optimum
is verified by ground-truth CFD before it is reported**; no optimum is claimed on a
surrogate prediction alone; best-of-N reporting is selection-bias-aware (held-out CFD
verification). This is the **CFD-VERIFIED-OPTIMUM-ONLY** rule.

### 3.6 Unsteady / phase-averaged post-processing
Flapping is periodic. Add: periodic-steady-state (cycle-convergence) detection,
phase-averaged loads over the stroke cycle, thrust/lift vs Strouhal number (propulsive
optimum St ≈ 0.2–0.4), leading-edge-vortex and wake visualization, power/efficiency
metrics, and viscous/pressure force decomposition. Steady scalar extraction (the current
Ofpp path) is insufficient. *(Stage 11.)*

### 3.7 Results must travel
The platform's outputs must be citable away from the cluster. Every exported result is a
**self-describing bundle**: `CaseSpec` + four-tuple + U95 envelope + validity context (+
RO-Crate / W3C-PROV alignment). The `aero/` core is already topology-agnostic (no IPs /
LXC IDs — those live only in `conf/` + docs), so this is about the *artifact format*,
not de-hardwiring code. *(Stage 20; the **RESULTS-MUST-TRAVEL** rule.)*

---

## 4. Validation ladder (replaces DPW-7 / HLPW-5)

Same harness, same tolerance discipline (a tolerance is a contract — never relaxed),
bio-relevant references validated against **experiment / DNS**, not CFD-vs-CFD alone
(the **VALIDATE-AGAINST-EXPERIMENT** rule). Reference data is acquired DVC-tracked under
`data/reference/<case>/` inside the owning stage.

| Tier | Case | Reference | Owning stage |
|---|---|---|---|
| Solver credibility (table-stakes) | NASA TMR flat plate, 2D bump, NACA 0012 | NASA TMR | retained (Stage 10 go/no-go) |
| Forward-regime credibility | Laminar flat plate (Blasius); low-Re cylinder vortex-shedding Strouhal; a laminar/transitional airfoil | Blasius; canonical cylinder Strouhal; transition data | Stage 10 (added — the mission's actual regime) |
| Unsteady machinery | Pitching / plunging airfoil | McCroskey dynamic-stall (NASA TM-84245); Heathcote-Gursul flexible foil | Stage 13 |
| **Flapping wing (flagship)** | Revolving/flapping wing, rigid then flexible | **Dickinson et al. (1999)** Robofly forces; Wang-Birch-Dickinson (2004) | Stage 14 (rigid), Stage 19 (flexible) |
| FSI machinery | Turek-Hron FSI3 | Turek & Hron (2006) — verified on the supported preCICE tutorial (deal.II/Nutils), ADR-016 | Stage 18 |
| **Optimization delta (the mission)** | A CFD-verified improvement on a parametric flapping case | held-out ground-truth CFD; delta > k·U95 | Stage 15 (thesis checkpoint) |

---

## 5. "Done enough to publish" for this mission

1. The forward solver passes the Stage-10 canonical go/no-go (table-stakes + forward-
   regime cases within tolerance); and
2. At least one **CFD-verified optimization delta** on a parametric flapping case exceeds
   its combined U95 (the Stage-15 thesis checkpoint); and
3. Every reported number carries its four-tuple + U95 envelope + validity context.

Not: "the agent layer works" or "a surrogate trained." Those are not the bar.

---

## 6. Prioritized backlog (problem-agnostic; maps to the Stage 10–20 map in `README-handoff.md`)

**P0 — make the forward problem trustworthy (hard gate for everything):**
1. **Fix the failing V&V** (NACA 0012 Cd, flat-plate Cf, 2D bump) **and add the
   forward-regime canonical cases** (Blasius, low-Re cylinder, transitional airfoil).
   Until the canonical set passes, no optimization or flapping result is thesis-grade.
   Stage 10 is a **hard go/no-go** — fix to tolerance or STOP and rethink.
2. Define the **output-validity bar** (`docs/vv/output-validity-bar.md` +
   `aero/vv/reportable.py`).

**P1 — build the forward flapping capability + the optimizer:**
3. Moving-mesh OpenFOAM path + unsteady/phase-averaged post-processing (§3.1, §3.6).
4. Small-signal/statistical UQ core (§3.4); the IMPROVEMENT-EXCEEDS-UNCERTAINTY gate.
5. Transition path (§3.3) + unsteady-airfoil validation.
6. Rigid flapping validation (Dickinson/Wang).
7. **CFD-in-the-loop parametric optimization** (Bayesian-opt; CFD-verified delta) —
   *the thesis checkpoint.*

**P2 — accelerate, broaden, and deepen the optimizer:**
8. Surrogate-accelerated optimization (own-data factory; verify optima with CFD).
9. Arbitrary-geometry ingestion + robust meshing (§3.2).
10. preCICE/CalculiX FSI + flexible flapping (flagship capstone).
11. Flexible-flapping optimization; portable result bundles; v0.1.0.

**Post-v0.1.0 (committed, named, further out):** adjoint shape/topology optimization
(DAFoam v5 + SU2 adjoint) → generative / true-topology proposers.

**Deferred indefinitely:** NeMo agent layer, literature miner, MoE, DPW/HLPW, riblet DNS.

---

## 7. Directive: do NOT start over

Stages 1–8 (provenance backbone, conventions, Proxmox provisioning, the five solver
adapters, the surrogate framework) are the expensive, correct, mission-agnostic core.
Rebuilding them would be the bigger mistake. The work is to **re-aim from Stage 10**
around the optimizer mission, close the §3 gaps, and pass the Stage-10 go/no-go. Keep the
provenance backbone, the conventions, the walking-skeleton discipline, the `Solver` /
`Surrogate` protocols, and the certificate framework exactly as they are.

---

## 8. Mission invariants (added to CLAUDE.md; two promoted to the Constitution)

1. **IMPROVEMENT-EXCEEDS-UNCERTAINTY** (Constitution Invariant 10). No reported effect or
   claimed improvement is thesis-grade unless its CFD-verified delta exceeds combined U95
   (k ≥ 1, default 2). U95 = RSS(numerical, statistical, input). The error bar is the
   result.
2. **NO-SURROGATE-ON-FOREIGN-DATA** (Constitution Invariant 11). Surrogates train only on
   the platform's own validated CFD; foreign datasets (automotive/aircraft) cannot
   produce a `validated`/`production` certificate.
3. **CFD-VERIFIED-OPTIMUM-ONLY** (CLAUDE.md; promotes to Constitution at Stage 15). Every
   reported optimum is verified by ground-truth CFD; no surrogate-only claims;
   selection-bias-aware best-of-N reporting.
4. **VALIDATE-AGAINST-EXPERIMENT** (CLAUDE.md). Forward capabilities validate against
   experimental/DNS reference data (§4), not CFD-vs-CFD alone.
5. **RESULTS-MUST-TRAVEL** (CLAUDE.md; promotes at Stage 20). Every exported result is a
   self-describing bundle usable in a thesis without the cluster.
6. **SCOPE-GATE** (CLAUDE.md). New solvers/ML/agents/features stay deferred unless they
   serve the optimizer mission or the flapping flagship. Gates **effort allocation, not
   interface generality.**

---

## Appendix A — riblets as a demoted example (retained for reference only)

Riblets remain a valid *example* problem and a useful illustration of the small-signal
discipline, but are **not** a development priority and own **no roadmap stage**. The
science, corrected against primary sources for accuracy:
- Up to ~10% skin-friction reduction for thin-blade riblets near s⁺ ≈ 15; **8.2%** for an
  optimized trapezoidal-groove surface (Bechert et al., JFM 338, 1997).
- Viscous-regime optimum near a groove length scale **lg⁺ ≈ 11**; breakdown
  (Kelvin-Helmholtz rollers) above **s⁺ ≈ 24** (García-Mayoral & Jiménez, JFM 678, 2011)
  — *the original "breakdown above s⁺ ≈ 20" was imprecise.*
- ~**6–8%** net drag reduction at flight Reynolds number (Spalart & McLean 2011; T-33
  flight tests) — *the original "~5%" was low.*
- The matched-condition **delta-drag** comparison (riblet vs smooth wall at identical
  conditions, correlated errors cancelling) is the methodological seed of the
  IMPROVEMENT-EXCEEDS-UNCERTAINTY invariant (§3.4) — that idea generalizes and is kept;
  the riblet stages do not.

If riblets are ever pursued, they would re-activate PyFR/NekRS (frozen-optional) and a
minimal-span channel methodology (MacDonald et al., JFM 816, 2017) — but only under the
SCOPE-GATE, as a plugged-in problem, not a core capability.

---

## Repo-reality corrections folded in (agent-verified, 2026-06-10)

Four claims from the earlier refocus draft were factually wrong about the repo and are
corrected here (and recorded in ADR-013):
1. **Turek-Hron FSI3 is NOT already built** — `aero/adapters/precice/` and
   `aero/vv/fsi/` are `.gitkeep` stubs. FSI is the new Stage 18.
2. **Stage 09 is NOT "just prompts"** — Phases 1–2 are done (DoMINO host code + a signed
   15 GB `physicsnemo.sif` + 484 DrivAerML runs / ~353 GiB DVC-tracked). The cut
   therefore **freezes** real artifacts (not deletes) and **cancels** a planned $67–191
   training run (ADR-013).
3. **The platform is NOT "hard-wired to one topology"** — the `aero/` core has zero
   IPs/LXC IDs; topology lives only in `conf/*.yaml` + `docs/`. The RESULTS-MUST-TRAVEL
   ask (§3.7) stands on the *artifact format*, not on de-hardwiring code.
4. **The surrogate machinery is already dataset-agnostic** — `Surrogate` ABC,
   `CertificateOfValidity`, and the taint union are generic; automotive specificity was
   isolated to `aero/surrogates/_common/loaders/`. "Repurpose for own data" is cheap.
