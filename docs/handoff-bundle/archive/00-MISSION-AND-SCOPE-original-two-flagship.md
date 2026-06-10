# 00-MISSION-AND-SCOPE — bio-inspired aero refocus

**Paste this file alongside `00-CONTEXT-project-brief.md` in every Claude Code
session. Where this file conflicts with the scope or validation choices in the
project brief, THIS FILE GOVERNS.** The brief describes a generic "do-everything"
aerodynamics platform; this file states what the platform is actually *for* and
re-scopes accordingly. Per the project's own convention (propose scope updates as
a new document, don't silently override), this is that update.

This file is written for future sessions that will NOT have the chat history or
the external audit that produced it. Everything you need to course-correct is here.

---

## 1. The actual mission (this was missing from the brief)

`aero-research-platform` is a **reproducible, validation-gated platform for
bio-inspired aerodynamics research**, on which researchers test novel concepts and
produce **thesis-citable, peer-defensible data**. Two flagship problem classes
define every scope decision:

1. **Flapping-wing aerodynamics.** Unsteady, low-to-moderate Reynolds number
   (Re ≈ 10²–10⁴ for insects, higher for birds/bats), leading-edge-vortex–dominated
   lift, prescribed *or* flexible (FSI) kinematics, moving/deforming geometry.

2. **Bio-inspired passive drag reduction** ("shark-scale" / riblet / denticle
   surfaces). A **small-signal, near-wall turbulence problem** — the effect is only
   ~3–10% drag reduction and lives in the viscous sublayer.

The platform's value proposition is not breadth of solvers. It is: *a researcher
brings a new bio-inspired concept, runs it here, and walks away with a result whose
provenance, validation, and uncertainty are good enough to put in a thesis and
defend to a reviewer.*

**Consequence for every future session:** ask of any proposed work, "does this
serve flapping-wing or riblet/denticle research, and does it raise the bar on
reproducibility or validation?" If not, it is out of scope until that changes.

---

## 2. Re-scoping (this is the core correction)

The mission re-weights the existing plan dramatically. Some components the original
brief treated as optional are mission-critical; the entire automotive-ML and
transport-aircraft-validation half is close to irrelevant.

| Component | Original brief | **Revised** | Why (science, not preference) |
|---|---|---|---|
| Provenance backbone (four-tuple, DVC/MLflow) | Core | **Core — untouched** | Thesis-grade reproducibility is the whole point. Best part of the build. |
| OpenFOAM-ESI | Core | **Core** | Workhorse for flapping moving-mesh + cheap iteration. |
| **PyFR (high-order, GPU)** | "another solver" | **Core** | Riblet drag reduction is a near-wall turbulence effect RANS cannot predict. Wall-resolved LES/DNS *is* the riblet science. |
| **preCICE + CalculiX (FSI)** | "nice demo" (Stage 11) | **Core** | Flexible flapping *is* FSI. Not optional for the bio mission. |
| NekRS | another GPU solver | **Keep, optional** | Canonical turbulent-channel DNS validation + scaling. Harder to mesh riblet geometry than PyFR. |
| SU2 (already built) | Core | **Keep, nice-to-have** | Bio flows are mostly low-Mach/incompressible. Useful but not load-bearing. Don't remove what's built. |
| DAFoam (adjoint) | listed | **Defer — but mission-relevant later** | Adjoint-optimized riblet geometry is a real research direction. Phase 2. |
| JAX-Fluids 2.0 | Core | **Defer** | Compressible Cartesian-mesh solver. Useful for ML-coupling research someday; orthogonal now. |
| DoMINO / Transolver / FIGConvNet / X-MGN on DrivAerML | Core (Stages 9–10) | **CUT (as designed)** | Trained on **car shapes**. Predicts nothing about wings or riblets. The certificate framework is good; DrivAerML is the wrong fuel. |
| Mixture-of-Experts gate | Core | **CUT** | Pure engineering surface, zero payoff for bio aero. |
| Surrogate *framework* (`Surrogate` protocol, certificate-of-validity) | Core | **Keep, repurpose — Phase 2** | Excellent pattern. Train on YOUR validated bio-aero data later, never on cars. |
| DPW-7 / HLPW-5 validation (Stage 12) | Core | **CUT** | Transport-aircraft cruise. Irrelevant to low-Re unsteady / wall-turbulence work. Replace with bio-relevant validation (§4). |
| NASA TMR cases | Core (Stage 5) | **Keep** | Fine turbulence-model baseline; flat plate underpins riblet wall-turbulence work. |
| UQpy / Dakota UQ | Core (Stage 12) | **Core — reframed** | For small-signal drag reduction, the error bars *are* the science (§3.4). |
| NeMo Agent Toolkit + AI-Q fork (Stage 14) | Core | **Defer indefinitely** | Scope creep. Also ahead of its ecosystem (AI-Q pins `nvidia-nat==1.4.0`; agentic CFD tops out ~68% physical fidelity even at SOTA). |
| Literature miner (Stage 15) | Core | **Defer indefinitely** | Nice-to-have, not science. A reference manager is enough for now. |
| Zenodo DOI + CITATION.cff + JOSS | Core | **Keep** | Citability is part of "thesis-grade." Cheap to maintain. |

**Net effect:** the solver fleet shrinks from six to **two-plus-coupling**
(OpenFOAM + PyFR + preCICE/CalculiX, with NekRS/SU2 as kept-optional). The ML half
is deferred to phase 2 and re-pointed at self-generated data. Validation is
re-aimed from aircraft/cars to bio experiments and DNS. You lose nothing you'll
miss and reclaim most of your time.

---

## 3. Science-driven requirements the brief omits (gaps to close)

### 3.1 Moving-mesh / overset for flapping
Prescribed-kinematics flapping needs dynamic/overset mesh (e.g. OpenFOAM
`overPimpleDyMFoam`). **The OpenFOAM adapter currently has no moving-mesh path.**
This is a prerequisite for *any* rigid flapping case and must precede flapping V&V.

### 3.2 Riblet-resolving meshing + viscous scaling
Riblet DNS/LES needs purpose-built near-wall meshing: parametric riblet geometry
generation (blade / scalloped / trapezoidal / shark-denticle profiles) and control
of spacing in wall units **s⁺ = s·u_τ/ν**, with the drag-reduction optimum near
**s⁺ ≈ 15–20** and the breakdown regime above ~s⁺ ≈ 20 (García-Mayoral & Jiménez).
The generic high-order mesh utilities do not cover this.

### 3.3 Transition modeling
Bio Reynolds numbers are *transitional* (laminar separation bubbles, transition on
flapping wings). Fully-turbulent RANS is wrong here. Add a transition path:
**γ-Reθ (Langtry–Menter)** for RANS, or rely on scale-resolving LES which captures
transition directly. TMR validation alone does not exercise this.

### 3.4 Small-signal drag decomposition + UQ-as-science
You will claim drag-reduction percentages smaller than typical CFD uncertainty.
Therefore:
- **Decompose drag** into viscous and pressure components (and per-surface) so the
  riblet mechanism is visible, not just the net number.
- **UQ is not optional bureaucracy.** A 6% drag-reduction claim with ±5% solver
  uncertainty is not publishable. The `production` gate requiring a UQ envelope is
  *correct*, but reframe it: prefer Latin Hypercube / polynomial chaos over the
  cheap *surrogate or coarse model* for parameter sweeps, and reserve expensive
  high-fidelity UQ for the final confirmation. The error bar must be tighter than
  the effect.

### 3.5 Experiment-vs-CFD validation (not just CFD-vs-CFD)
Bio work is validated against experiments and DNS, not workshop consensus bands.
Build the validation ladder in §4. Co-locate each reference dataset with license
and citation, DVC-tracked, exactly as the TMR cases already are.

### 3.6 Unsteady / phase-averaged post-processing
Flapping is periodic. Add: phase-averaged loads over the stroke cycle, thrust/lift
coefficient vs Strouhal number (propulsive optimum St ≈ 0.2–0.4), wake and
leading-edge-vortex visualization, power/efficiency metrics. Steady scalar
extraction (current Ofpp path) is insufficient.

### 3.7 Portability for the "platform for researchers" goal
The platform is hard-wired to one Proxmox/TrueNAS topology (specific LXC IDs, NFS
mounts, named hosts). For others to produce thesis-citable data:
- **Near term:** run it as a single instance; make the *artifacts* portable — a
  researcher's `CaseSpec`, result bundle, four-tuple, and validity certificate must
  be self-describing and travel into a thesis without the cluster.
- **Long term:** de-hardwire into a deployable stack (containerize the provenance
  services; parameterize hosts; no baked-in LXC IDs). **Do not build multi-tenancy
  yet**, but stop hard-coding topology so the later port is cheap.

---

## 4. Re-scoped validation ladder (replaces DPW-7 / HLPW-5)

Build these instead of the transport-aircraft cases. Same harness, same tolerances
discipline, bio-relevant references.

| Tier | Case | Reference (validate against) | Purpose |
|---|---|---|---|
| Wall turbulence baseline | Turbulent channel flow, smooth wall | Moser–Kim–Mansour (1999) DNS; Lee–Moser (2015) high-Re DNS | The substrate riblet DNS is built on. Must be right first. |
| **Riblet drag reduction** | Riblet-walled channel/boundary layer, s⁺ sweep | **Bechert et al. (1997) JFM** experimental drag curve; García-Mayoral & Jiménez DNS | The core riblet science. Reproduce the drag-reduction-vs-s⁺ curve. |
| Transition | Flat plate / airfoil at low Re with LSB | Published transition-onset data; γ-Reθ benchmarks | Confirms transitional capability for bio Re. |
| Unsteady airfoil | Pitching/plunging airfoil | Canonical unsteady aerodynamics data (e.g. McCroskey dynamic stall; Heathcote–Gursul flexible foil) | Validates unsteady/moving-mesh machinery. |
| **Flapping wing** | Revolving/flapping wing, rigid then flexible | **Dickinson et al. (1999)** Robofly forces; Wang–Birch–Dickinson (2004) | The core flapping science. LEV-dominated lift. |
| FSI machinery | Turek-Hron FSI3 (already built) | Turek & Hron (2006) | Validates the *coupling*, not the bio physics. Keep. |
| Turbulence models | TMR flat plate, 2D bump, NACA 0012 (already built) | NASA TMR | General solver/turbulence-model baseline. Keep. |

Applied proof point worth citing in the thesis framing: the AeroSHARK riblet film
(Lufthansa Technik / BASF) demonstrates real-world riblet drag reduction in service.

---

## 5. Honest current-state ledger (as of v0.0.8 / Stage 08)

Future sessions: **do not trust any "validated" claim until you see the numbers.**

**Built and broadly trustworthy:**
- Stages 1–4: scaffolding, conventions, Proxmox provisioning, and the **four-tuple
  provenance backbone (git SHA + DVC hash + SIF SHA256 + config hash)**. This is the
  strongest part of the project. Treat it as settled foundation; do not churn it.
- OpenFOAM walking skeleton (NACA 0012 end-to-end) and SU2 adapter exist.
- PyFR / NekRS adapters and JAX-Fluids + surrogate *plumbing* exist.

**Built but FAILING / not yet trustworthy (from the CHANGELOG):**
- NACA 0012 Cd is **+21%** vs reference (trailing-edge pressure-drag resolution).
- Turbulent flat-plate Cf is **7–15%** off the correlation.
- 2D bump solve **stalls on high-aspect-ratio cells**.
- These are marked xfail with "no tolerance was relaxed" — honest, but it means the
  stated V&V tolerances (Cd 3%, Cf 5%, Cp 3%) are **not currently met**. Closing this
  is hard CFD craft (mesh quality, y⁺, schemes, BCs), not a one-session fix. For the
  riblet mission this is *blocking*: you cannot resolve a small-signal drag effect on
  a solver that is 7–21% off on canonical cases.

**Planned but not built (just stage prompts):** everything from Stage 09 onward.
This is good news — it means re-aiming Stages 09–16 around §2 costs almost nothing.

**"Done enough to publish" for THIS mission means:**
1. The smooth-wall and riblet validation tier (§4) passes with a demonstrated
   uncertainty *tighter than the drag-reduction effect you report*; and
2. At least one flapping case reproduces published forces within stated tolerance;
   and
3. Every reported number carries its four-tuple + UQ envelope + validity context.
Not: "the agent layer works" or "four surrogates trained." Those are not the bar.

---

## 6. Prioritized improvement backlog for future sessions

**P0 — unblock the core science (do these before anything new):**
1. **Fix the failing V&V** (NACA 0012 Cd, flat-plate Cf, 2D bump). Mesh
   independence, y⁺ < 1, scheme/BC review. Until canonical cases pass, riblet
   results are meaningless. This is the single highest-value work in the project.
2. **Re-author Stage prompts 09–16** around §2: delete the DrivAerML-surrogate and
   DPW/HLPW stages; insert moving-mesh (§3.1), riblet meshing (§3.2), the §4
   validation ladder, and unsteady post-processing (§3.6).

**P1 — build the two flagship capabilities:**
3. **Moving-mesh OpenFOAM path** (§3.1) → rigid flapping → unsteady-airfoil
   validation (§4).
4. **Riblet meshing + s⁺ tooling** (§3.2) on PyFR → smooth-wall channel DNS →
   reproduce Bechert drag-reduction curve (§4).
5. **Transition path** (§3.3) for low-Re cases.
6. **UQ reframed for small-signal detection** (§3.4); drag decomposition.

**P2 — broaden and harden:**
7. Flexible-flapping FSI via the existing preCICE/CalculiX path (§4 FSI tier).
8. Portable artifact format (§3.7 near-term).
9. *Only now* consider surrogates — trained on your own validated runs, using the
   existing certificate framework. Never on automotive data.
10. DAFoam adjoint for riblet-shape optimization (phase 2).

**Explicitly deferred indefinitely:** agent layer, literature miner, MoE,
JAX-Fluids, DPW/HLPW, multi-tenant deployment.

---

## 7. Directive: do NOT start over

The foundation (Stages 1–4) and the reusable solver/validation work in 5–8 are the
expensive, correct, mission-agnostic core. Rebuilding them would be the bigger
mistake. The work is to **re-aim the trajectory from ~Stage 09**, fix the failing
V&V, and close the §3 gaps. Keep the provenance backbone, the conventions, the
walking-skeleton discipline, and the certificate-of-validity *framework* exactly as
they are.

---

## 8. Mission-specific invariants to add to CLAUDE.md

1. **SMALL-SIGNAL RULE.** No drag-reduction result is reportable unless its
   quantified uncertainty is smaller than the effect claimed. The error bar is the
   science.
2. **VALIDATE AGAINST EXPERIMENT.** Bio cases validate against experimental/DNS
   reference data (§4), not against other CFD runs or workshop consensus alone.
3. **NO SURROGATE ON FOREIGN DATA.** Surrogates train only on the platform's own
   validated bio-aero runs. Automotive/aircraft datasets are out of scope for
   training corpora.
4. **RESULTS MUST TRAVEL.** Every result a researcher exports carries a
   self-describing bundle (CaseSpec + four-tuple + UQ envelope + validity context)
   usable in a thesis without access to the cluster.
5. **SCOPE GATE.** New solvers, ML, agents, or literature features stay deferred
   unless they directly serve flapping-wing or riblet/denticle research. When
   tempted, re-read §1.
