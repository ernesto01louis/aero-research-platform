<!-- REPO STATUS (added 2026-06-10): Non-normative reference, partially adopted via ADR-013.
     Its capability-layer framing (Layers 0-1: reproducible core + surrogate-factory/discovery
     loop) and the "verify every optimum with ground-truth CFD" principle ARE core to the
     optimizer mission (docs/handoff-bundle/00-MISSION-AND-SCOPE.md). The rest is input, not a
     spec. This document does NOT govern; 00-MISSION-AND-SCOPE.md + the ADRs do. Verified
     2026-06-10: cross-domain automotive->airfoil surrogate transfer is unresolved in the
     literature, so the "automotive zoo is a category error" claim is reframed in ADR-013 as
     "no evidence it helps + own-data factory sidesteps it," not a proven non-transfer. -->

# Aerodynamics Research Platform — Architecture Briefing for Independent Review

> **A position paper to be challenged, not a spec to implement.** This document is a prior research synthesis. Your job (Claude Code) is to reason about it independently, verify its claims against current sources *and* the actual repository, agree or disagree with explicit reasons, and produce your own synthesis. Where your findings contradict this document, say so and reconcile against the repo and the operator's stated goals. The final section lists exactly what to verify and where to push back.

---

## 0. How to use this document (read first)

**What this is.** A critical architecture review of an open-source, scientific-grade aerodynamics *research platform*. It evaluates the technical stack that exists or is planned in the repo and recommends what to keep, re-aim, right-size, defer, or drop.

**What this is not.** It is not a set of marching orders, and it is not authoritative over the repo. Treat every claim as falsifiable. Two earlier framings in the prior draft were wrong and have been corrected here (see §1) — assume other things may be wrong too.

**Confidence tags.** Claims are tagged so you know how hard to lean on them:

- **[ESTABLISHED]** — well-supported by literature or primary sources. Spot-check, but these are solid.
- **[JUDGMENT]** — engineering opinion or synthesis, not a single citable result. Weigh it; you may disagree.
- **[VERIFY]** — time-sensitive or uncertain. Check against current sources or the repo before relying on it.

**Your task, in one line.** Independently research the same questions, compare your findings to this document and to the repo's actual state, and tell the operator where this review is right, where it is wrong, and what it missed. The concrete checklist is in §11.

---

## 1. What the platform is (corrected framing)

Two corrections from the operator that override the prior draft:

1. **"Thesis-grade" is a validity bar on the platform's *outputs*, not a research topic the platform is built to execute.** The deliverable is the *platform itself*. "Usable in a thesis or peer-reviewed work" describes the *rigor its results must reach* — validation against references, quantified uncertainty, complete provenance, end-to-end reproducibility — for **any** problem plugged into it. There is no committed thesis topic. Any prior text that "locked scope to a tubercle study" or said "build a thesis, not a platform" is wrong and is removed.

2. **The application areas are *examples*, not specializations.** Flapping-wing aerodynamics, shark-skin/riblet drag reduction, reverse wings, asymmetrical wings — these are illustrations of the *class* of problem the operator wants to be able to plug in. None is a fixed specialization. The platform is general-purpose; whatever the operator is working on should be pluggable. (NACA airfoils appear in this document only as canonical **verification benchmarks** — NACA 0012 is the standard CFD validation airfoil — never as "the research topic.")

**The "analytical AI model," restated honestly.** The operator's stated inspiration is AlphaFold/GNoME: a fast forward-prediction surrogate that accelerates/replaces CFD, plus — later — a generative/discovery loop that proposes novel candidate geometries, eventually combinable into one integrated system, ultimately ingesting user CAD/mesh geometry and optimizing it in a reproducible, ideally visually observable way.

For a *general* platform, this "AI model" is **not a single trained artifact**. It is a **surrogate factory + discovery loop**: a capability that, for each problem plugged in, builds a fit-for-purpose surrogate on the platform's *own* CFD over the bounded design space the operator defines, then runs surrogate-in-the-loop optimization/discovery with mandatory ground-truth-CFD verification of any result. The neural-operator architecture is a *choice within* that pipeline, selected per problem class. This reframing is the single most important idea in this document and it propagates through every section below. **[JUDGMENT]**

**The output-validity bar is the real product spec — and it is currently undefined.** Because "thesis-grade output" *is* the deliverable, the platform needs an explicit, operational definition of that bar: required validation tolerances against reference data, minimum UQ (e.g., grid-convergence index on every reported quantity), provenance completeness, and reproducibility criteria (a third party can re-run and land within stated bounds). Pinning this down is a first-order task, not a formality (see §11, item 10).

---

## 2. The central architecture decision: how surrogates work in a general platform

This is the most important technical question, and the repo currently answers it in a way this review judges to be misaimed.

**Three candidate architectures:**

- **(a) One pretrained foundation model** (literal AlphaFold analogy). **Infeasible near-term [ESTABLISHED].** Aerodynamics has no Protein-Data-Bank-scale curated dataset, the geometry space is continuous and effectively infinite-dimensional, and CFD verification per candidate is far more expensive than a DFT relaxation. See §3 for why the analogy is structurally false. A cross-regime aero foundation model is a legitimate *long-horizon research aspiration*, not a deliverable — and even then, transfer across flow regimes (attached vs separated, steady vs unsteady, incompressible vs transonic) is unproven.

- **(b) A fixed zoo of pretrained surrogates trained on automotive data** — the repo's current path (Stages 09–10: DoMINO, then Transolver / FIGConvNet / X-MeshGraphNet + a Mixture-of-Experts gate, all trained on DrivAerML / AhmedML / WindsorML). **This review judges this a category error for a general airfoil/wing platform [JUDGMENT — verify, this is load-bearing].** Reasoning: automotive external aero is bluff-body, massively separated, pressure/wake-dominated flow on ~10⁸-cell meshes. Wing/airfoil problems — and most of the operator's examples — turn on attached flow, separation onset, post-stall behaviour, leading-edge vortices, and near-wall turbulence, where the quantities of interest are exquisitely sensitive to boundary-layer detail. Features learned on vehicle-wake topology are not expected to transfer. Separately, a *fixed* zoo cannot cover arbitrary plug-in problems by construction.

- **(c) A surrogate factory** — for each campaign, build a surrogate on the platform's own cheap, bounded CFD over the design space the operator defines for that problem. **This review recommends (c) as the load-bearing architecture [JUDGMENT].** The workflow per problem: define geometry parametrization + design-space bounds → generate N CFD samples (grow by active learning) → train a geometry-aware surrogate → validate against held-out CFD and any reference data → run surrogate-in-the-loop optimization/discovery → **verify optima with ground-truth CFD** before reporting.

**What survives from the repo's surrogate work.** The *scaffolding* is good and reusable: the `Surrogate` protocol, the `CertificateOfValidity` framework (training distribution, held-out error, applicability envelope, expiry), and the four-tuple provenance hook. **Keep these.** What should leave the critical path is the *automotive datasets and the four-model automotive zoo as the destination*. Re-aim Stages 09–10 from "train fixed automotive models" to "the surrogate factory, demonstrated on a representative self-generated dataset." **[JUDGMENT]**

**Data scale — general guidance, not a topic-specific number.** For a tightly bounded, low-dimensional design space, **~150–500 of your own CFD runs is a sound starting target [ESTABLISHED for 2D airfoil-class problems; VERIFY for anything 3D / unsteady / separated, where the number climbs].** Evidence: AirfRANS (Bonnet et al., NeurIPS 2022) ships a deliberate **scarce-data regime of 200 training samples** (1,000 incompressible OpenFOAM Spalart–Allmaras airfoil cases total); GINO (Li et al., NeurIPS 2023) trained on **~500 samples** for car-surface pressure with a reported ~26,000× drag-coefficient speedup over GPU CFD; the NeurIPS 2024 ML4CFD competition ran AirfRANS with as few as ~103 examples. Treat these as order-of-magnitude anchors. If a surrogate underfits (e.g., near stall, or in separated regions), grow the dataset by **active learning** rather than blanket sampling.

**Surrogate architecture is a per-problem choice [VERIFY].** Do not assume one operator family is universal. The current landscape (2023–2026):

- **FNO / Geo-FNO / GINO** — resolution-invariant spectral operators; GINO couples a graph-neural-operator encoder (arbitrary point clouds / SDFs) to an FNO core, discretization-convergent. Good general default for geometry-conditioned fields; degrades where boundaries are undersampled near sharp/high-curvature features.
- **Transformer operators — Transolver / Transolver++ / GNOT / OFormer / AB-UPT** — attention over physical tokens. Transolver scales poorly to very large meshes without sequence parallelism; **AB-UPT** (Alkin et al. 2025) is current automotive SOTA (9M surface / 140M volume cells on one GPU, ~1-day training, divergence-free formulation).
- **Graph / point models — MeshGraphNet / X-MeshGraphNet / FIGConvNet / DoMINO** — mesh-independent, multi-scale; DoMINO is the PhysicsNeMo baseline (trained on DrivAerML, ~160M-point meshes).
- **Neural fields — MARIO / enf2enf / GAOT** — geometry as a modulated implicit field; **GAOT** (ETH, NeurIPS 2025) reportedly outperforms GINO/Transolver/RIGNO on throughput and accuracy, including on AirfRANS.

For a first surrogate-factory implementation, a Geo-FNO / GINO / neural-field core is a reasonable default; the right choice for a *specific* plugged-in problem (3D wing, unsteady flapping, near-wall riblets) should be re-decided against current benchmarks and the problem's data/compute budget.

**Optimization route.** Three options: **(1) surrogate + Bayesian optimization** — sample-efficient, robust to noisy/expensive evaluations, ideal for ≲10 design variables; the right default. **(2) surrogate + genetic algorithm** — good for cross-validation against published GA optima. **(3) differentiable CFD or differentiable surrogate + gradient descent** (JAX-Fluids / JAX-CFD / PhiFlow) — powerful for high-dimensional/unsteady problems, steep robustness/engineering cost; a later cross-cutting capability, not a starting requirement. **[ESTABLISHED]**

---

## 3. The generative / discovery loop (the AlphaFold / GNoME analogy, honestly)

**The analogy is structurally false and should be reframed [ESTABLISHED].** AlphaFold succeeded on the Protein Data Bank (a giant, curated, decades-old dataset) and a constrained output (residue coordinates of a known sequence). GNoME (Merchant et al., Nature 2023) bootstrapped from the Materials Project (~69k DFT-relaxed structures in its 2021 snapshot) and operated in a quasi-discrete, symmetry-constrained space verifiable by DFT — reporting ~2.2M candidate structures, **381,000 newly stable materials**, with per-trial hit rates rising well above prior work, expanding the known stable-crystal set roughly from 48,000 to 421,000. Aerodynamic geometry optimization has **neither** a PDB-scale curated dataset **nor** a discrete, cheaply-verifiable output space; CFD verification is expensive and the geometry space is continuous.

**The honest version of "an AlphaFold for aerodynamics"** is therefore the loop GNoME, FunSearch, and AlphaEvolve actually run: a **proposer** (a performance-conditioned generative model or a parametric sampler) coupled to a **cheap evaluator** (the surrogate) inside an **active-learning loop**, where a small number of proposals are verified by ground-truth CFD and fed back as training data — a data flywheel. FunSearch and AlphaEvolve (DeepMind) pair an LLM proposer with an automated evaluator and evolutionary selection; AlphaEvolve's headline results (an improvement to 4×4 complex matrix multiplication; a ~0.7% recovery of Google's worldwide compute via a better scheduling heuristic) all relied on a **programmatic ground-truth verifier** that gates hallucinations. **The loop architecture transfers; the dataset scale does not. [ESTABLISHED]**

**Generative geometry already works in 2D and is the seed of the north star.** Performance-conditioned airfoil generation: Airfoil Diffusion (Graves & Barati Farimani, arXiv 2408.15898), DiffAirfoil (latent-space diffusion for shape optimization), AirfoilGen (2026, "valid-by-construction" representation). A 2026 study compares coordinate vs PCA vs SDF encodings (coordinate best for 2D; SDF the scalable path to 3D). For 3D, the relevant literature is point-cloud diffusion, neural-implicit/SDF generation, and inverse-design lattices; **CDFAM** (Computational Design, Fabrication & Manufacturing — AI-driven generative engineering design) is the venue to track. These proposers pair directly with the surrogate-factory evaluator from §2. **[ESTABLISHED]**

**Design against documented AI-scientist failure modes [ESTABLISHED — and central to credibility].** Luo, Kasirzadeh & Shah (arXiv:2509.08713, "The More You Automate, the Less You See") identify four failure modes in autonomous AI-scientist systems: **inappropriate benchmark selection, data leakage, metric misuse, and post-hoc selection bias**. For an aerodynamics discovery loop these map to: train/test geometries leaking through shared meshes; reporting the surrogate's optimistic coefficients without CFD verification; and cherry-picking the best of many generated candidates. The mitigation is the platform's provenance contract plus a **hard rule: every claimed optimum is verified by held-out ground-truth CFD before it is reported.** This rule is what lets the platform's outputs clear the validity bar in §1.

---

## 4. Geometry: ingestion, representation, editing, and output

This section is *elevated* relative to the prior draft, because "plug in a 3D file and optimize it" is the operator's stated north star, not a thesis aside.

**Mesh vs parametric CAD is a genuine difficulty cliff [ESTABLISHED].** Editing meshes (STL/3MF) in an optimization loop is comparatively easy: free-form deformation, mesh morphing, and SDF representations support smooth, differentiable shape change. Editing *parametric* CAD (STEP/BREP) automatically is much harder — it needs a geometric kernel (OpenCASCADE) and a programmatic modelling layer. The mature open-source options are **CadQuery** and **build123d** (both Python, both on the OCCT/OCP kernel, both export STEP/STL/3MF; build123d is the more Pythonic evolution, and they share the OCP wrapper so objects interchange). Text-to-CadQuery (LLM-generated CAD scripts) hints at a generative-CAD direction but is not yet production-grade.

**Representation ranking for optimization [JUDGMENT]:** SDF / neural-implicit (smooth, differentiable, scalable to 3D, marching-cubes to mesh) > free-form deformation / mesh morphing (preserves topology, easy gradients) > NURBS / parametric-with-design-parameters (compact, manufacturable, constrained) > raw mesh (flexible, can self-intersect). **Pragmatic pattern: optimize in a parametric or SDF space, then emit CAD via CadQuery/build123d** so outputs are manufacturable and reproducible.

**Automated meshing from arbitrary geometry is the single biggest robustness risk for the north star [ESTABLISHED].** snappyHexMesh, gmsh, and cfMesh all struggle on never-before-seen, non-watertight, or thin-feature geometry. For scripted parametric geometry this is reliable; for "ingest any user CAD," meshing failure on adversarial input is the dominant practical failure mode and must be sandboxed with validation/repair (watertightness checks, automatic mesh-quality gating, fallback strategies).

**"Visually observable" editing** is a Layer-4 usability capability: render intermediate geometries/fields per iteration via PyVista, ParaView, or a three.js / Blender-headless front-end. It carries no scientific payoff and real engineering overhead; the operator's stated willingness to settle for final-output rendering is reasonable. Render the final optimized geometry and a few key iterations; defer live editing visualization. **[JUDGMENT]**

---

## 5. Solvers, fidelity, and V&V (the validity engine)

**The five-solver fleet is over-scoped to populate at once, but the abstraction is right [JUDGMENT].** Keep `SolverProtocol`; populate it lazily as capability layers demand. Verdict by need:

- **Steady RANS core (most problems' entry point):** OpenFOAM alone suffices; SU2 is a reasonable second for cross-validation and adjoint sensitivities.
- **Unsteady + moving boundary (e.g., flapping wing):** OpenFOAM + preCICE + a structural solver (CalculiX) is the validated open-source path; requires dynamic/overset meshing — a major step.
- **Near-wall turbulence (e.g., riblets):** wall-resolved LES/DNS, a different regime; a GPU spectral/FD code (NekRS, or CaNS/CaLES-class) is appropriate.

PyFR, NekRS, and JAX-Fluids are each justified only by specific later capabilities (high-order/GPU scale-resolving; differentiable optimization). Carrying all five now is maintenance burden without payoff.

**V&V is load-bearing, not overhead — this corrects the prior draft.** Because the platform's product *is* output validity (§1), a verification-and-validation harness is the heart of the system, not a trim target. The right principle is **incremental, per-capability V&V**: every capability layer ships with at least one validated canonical benchmark before it is trusted on a novel problem. A sensible benchmark menu, expanded over time: flat-plate boundary layer and a NACA-airfoil polar vs **NASA Turbulence Modeling Resource** (steady RANS); backward-facing step / periodic hill and **Taylor–Green vortex** (scale-resolving); **Turek–Hron** (FSI); a **minimal-span channel** (near-wall/riblets). The repo's existing V&V direction (NASA TMR, DPW/HLPW subsets, Taylor–Green, periodic hill) is sound; the right-sizing is **don't front-load the entire DPW-7/HLPW-5 workshop suite on day one** — grow the menu with the capabilities. **[JUDGMENT]**

**UQ, proportionate.** Every reported result should carry at minimum a **grid-convergence index** and a surrogate-error envelope; richer UQ (Dakota / UQpy) is added as a capability layer, not stood up wholesale at the start. This keeps the validity bar honest without UQ infrastructure consuming the schedule. **[JUDGMENT]**

**Near-wall turbulence (riblets) — feasibility and required fidelity, kept as an example capability [ESTABLISHED].** This is included because riblets are a frequently-cited example, and because the fidelity question generalizes to any near-wall study. Validated science: up to ~10% skin-friction reduction for thin-blade riblets at s⁺≈15, and **8.2% for an optimized trapezoidal-groove surface** (Bechert et al., JFM 338, 1997); viscous-regime optimum at s⁺∈[10,20] (García-Mayoral & Jiménez, JFM 678, 2011); dropping to ~5% at flight Reynolds number (Spalart & McLean 2011), consistent with in-service riblet-film results. Riblet-resolving DNS needs roughly Δx⁺≤9, Δy⁺≤4, and ≥32 spanwise points per riblet period (Modesti et al., JFM 917, 2021; Choi–Moin–Kim, JFM 255, 1993). The **minimal-span channel** methodology (MacDonald et al., JFM 816, 2017) reduces cost from scaling as Reτ^(9/4) to ks⁺^(9/4) — explicitly framed as feasible on high-end desktop-class hardware; modern GPU solvers (CaNS/CaLES; ~283M cells on one A100) make individual low-Reτ cases tractable in hours-to-days, and published ~20-case minimal-span sweeps confirm parametric studies are university-cluster scale. **Verdict: credibly studyable on a homelab + modest cloud IF restricted to minimal-span, low-moderate Reτ; flight-Re full-span DNS needs national HPC.** The same fidelity-vs-cost logic should be applied to *any* near-wall problem plugged in.

**FSI (e.g., flapping wing) cost [ESTABLISHED].** preCICE 3 is the right coupling library; the OpenFOAM–CalculiX adapter is mature and used in published flapping-wing FSI. Strong-coupling unsteady moving-boundary simulation is expensive (added-mass instabilities, per-timestep sub-iterations, remeshing) — plan it as a multi-month capability layer, not a sprint.

---

## 6. Provenance, reproducibility, observability, open-source

**The four-tuple contract is exemplary and ahead of most published work [ESTABLISHED].** Logging `(git_sha, dvc_input_hash, container_sif_sha256, config_hash)` to MLflow on every CFD and ML run, with DVC + Postgres + MinIO and SHA256-pinned Apptainer/SIF containers, exceeds the rigor of most published CFD/ML and directly defends against the data-leakage failure mode from §3. The per-surrogate `CertificateOfValidity` (training distribution, held-out error, applicability envelope, expiry) is genuinely good practice rarely seen in the wild. **This is a differentiator; keep it.**

**Gaps are standards-alignment, not missing rigor [ESTABLISHED]:**
- Adopt **RO-Crate** and/or **W3C PROV** so provenance is machine-readable and portable rather than bespoke.
- Mint **Zenodo DOIs** for datasets and model snapshots (FAIR principles).
- Add **CITATION.cff** and semantic versioning from day one.
- Track an **ML-reproducibility checklist** (NeurIPS / MLCommons style) for each surrogate.

**Open-source release strategy [ESTABLISHED].** OpenFOAM is GPL; JAX-Fluids is MIT; PhysicsNeMo is Apache-2.0. A platform that *orchestrates* GPL solvers via subprocess/container calls (not linking) can itself be permissively licensed, but a copyleft-safe core choice is defensible — settle this early. **JOSS** is an excellent venue but note its constraints: **≥6 months of public development history before submission**, feature-complete, and **pre-trained ML models / notebooks are out of scope** — so a JOSS paper should describe the *platform/framework*, with surrogate models released separately (e.g., Hugging Face + Zenodo DOI). The reproducibility/observability requirements are not at risk of being under-built; the real risk is **reproducibility theater** — provenance work consuming time that should go to capability. Timebox it.

---

## 7. Orchestration and the agentic layer

**Consolidate to one orchestrator [JUDGMENT].** For a single-developer CFD/ML campaign engine: Prefect (Python-native, strong ML-iteration ergonomics, dynamic graphs, easy to unit-test) vs Snakemake (file-oriented, strong academic/reproducibility community, excellent on a single HPC node) vs Nextflow (process-oriented, best for cloud/multinode scale) vs Dask/Ray (distributed compute, not orchestration). **Recommendation: pick Prefect 3 *or* Snakemake and drop Covalent** — Prefect if the workload is ML-iteration-heavy and Python-centric; Snakemake if reproducibility/academic-sharing is paramount and runs stay on one cluster. Running Prefect + Covalent + a heavyweight agent stack + a separate orchestrator repo is at least two too many systems for one person.

**The agentic layer is premature as a research contribution but fine as a tool [JUDGMENT].** Agentic CFD is real and improving: **Foam-Agent 2.0** (arXiv:2509.18178) reports an 88.2% success rate on 110 OpenFOAM cases (LangGraph + MCP); **ChatCFD** (arXiv:2506.02019) reports 82.1% execution success on 315 cases and ~68% "physical fidelity." The wide spread between reported numbers across systems itself signals brittleness on novel cases. **Verdict:** the NVIDIA NeMo Agent Toolkit + AI-Q Blueprint fork is heavyweight and NVIDIA-ecosystem-locked; the operator's separate-repo choice of **LangGraph (core) + smolagents (code-heavy sub-tasks)** is better aligned with the open-source/observability goals and with where the field actually builds (Foam-Agent uses LangGraph + MCP). Run the agent as a **thin convenience wrapper** exposing MCP tools over solvers/meshers/V&V/UQ primitives — and **do not make autonomous agentic orchestration a claimed result**, because the documented brittleness plus the §3 failure modes would undermine the validity bar.

---

## 8. Capability-layered roadmap (problem-agnostic)

This replaces the prior topic-locked phasing. Layers are **capabilities**, each independently validated and independently useful; the operator plugs problems into whatever layers they need. The example problems below are *consumers* of a layer, not the layer's purpose.

- **Layer 0 — Reproducible single-fidelity core.** One solver (OpenFOAM), geometry parametrization + scripted meshing, the four-tuple provenance contract, and a V&V harness with ≥1 validated canonical benchmark. This layer is what makes every later output "thesis-grade." *Maps to repo Stages 01–05 — load-bearing, keep.*
- **Layer 1 — Surrogate factory + discovery loop.** The per-campaign surrogate-training pipeline (§2) + surrogate-in-the-loop optimization (Bayesian optimization first), with mandatory ground-truth-CFD verification of optima, demonstrated on ≥1 representative self-generated dataset. This is the "analytical AI model" capability. *Maps to repo Stages 08–10 — re-aim from automotive zoo to surrogate factory; keep the `Surrogate` protocol + `CertificateOfValidity`.*
- **Layer 2 — Physics-fidelity breadth.** Add scale-resolving (LES/DNS via a GPU solver) and/or compressible/transonic as problems demand; expand the V&V menu. *Example consumer: riblets / near-wall turbulence. Maps to repo Stages 06–07 (solver breadth) + 12 (expanded V&V/UQ, right-sized).*
- **Layer 3 — Unsteady + FSI.** preCICE + structural solver; dynamic/overset meshing. *Example consumer: flapping wing. Maps to repo Stage 11.*
- **Layer 4 — Generative discovery + geometry ingestion.** Performance-conditioned generative proposers (§3); CAD/STL/3MF ingestion via CadQuery/build123d (§4); robust automated meshing with validation/repair; optional visual observability; the integrated surrogate+generator system. *This is the north star — "plug in any geometry and optimize it."*
- **Cross-cutting — Differentiability.** JAX-Fluids / JAX-CFD / PhiFlow, introduced when gradient-based optimization earns its keep (typically alongside Layers 3–4). *Maps to repo Stage 08's differentiable-solver work — keep the adapter, defer heavy use.*

**Mapping to the repo's 16 stages — load-bearing / re-aim / right-size / defer:**
- *Load-bearing (keep):* scaffolding + infra + walking skeleton + provenance + initial V&V (Stages 01–05); the `Surrogate` protocol and certificate framework (within 08); preCICE/FSI (11); literature tooling as research support (15, don't over-invest); hardening/release (16).
- *Re-aim:* the surrogate destination (Stages 09–10) — from "train four fixed automotive models + MoE on DrivAer" to "the surrogate factory on self-generated data."
- *Right-size:* full V&V/UQ (Stage 12) — grow the benchmark menu and UQ depth per capability rather than standing up the whole DPW-7/HLPW-5 + Dakota/UQpy stack at once.
- *Defer:* multi-cloud cost router (Stage 13) — use one provider until scale demands it; the NeMo Agent Toolkit/AI-Q fork (Stage 14) — replace with a thin LangGraph + MCP wrapper later; Covalent — drop.

---

## 9. Budget

The original "$50/month cap" was an arbitrary placeholder; the operator is open to a recommended envelope as long as it stays well under five figures.

- **Baseline development: ~$50–150/month [VERIFY pricing].** Most steady-RANS sample generation runs on the Proxmox homelab CPU; surrogate training is a few GPU-hours on a rented A100/H100. Even 100–300 GPU-hours of experimentation per month is a few hundred dollars at specialized-provider rates.
- **Sustained multi-year: ~$200–600/month [VERIFY pricing]**, rising during active surrogate-training or scale-resolving campaigns.
- **Burst months: ~$1–2k** for a larger surrogate campaign or a minimal-span DNS sweep.
- **Total stays comfortably under five figures per year** — far below the "tens of thousands" ceiling.

Indicative 2026 rates (volatile — re-check live): H100 on-demand roughly $1.90–3.29/hr at specialized providers (up to $11+/hr at hyperscalers); A100 80GB roughly $1.07–1.99/hr; spot/community instances 40–60% cheaper for interruptible training. **[VERIFY]**

---

## 10. Risks and failure modes (single developer)

1. **Scope sprawl / never-shipping** — building every layer at low fidelity instead of completing Layer 0→1 to the validity bar. The highest risk.
2. **Surrogate over-trust** — reporting surrogate optima without ground-truth CFD verification (directly the §3 failure modes). The credibility killer.
3. **Meshing robustness** on novel geometry — the silent killer of "ingest any CAD" (§4).
4. **Maintenance burden** — five solvers + multiple orchestrators + a heavyweight agent stack exceeding one person's capacity (§5, §7).
5. **Fidelity creep** — attempting flight-Re full-span DNS or strongly-coupled FSI that needs HPC (§5).
6. **Reproducibility theater** — provenance/standards work crowding out capability (§6).
7. **Surrogate-transfer assumption being wrong in either direction** — if automotive features *do* transfer, the re-aim in §2 is partly unnecessary; if even airfoil→airfoil transfer is weak across regimes, the surrogate factory must retrain more aggressively than assumed. This is why §2's central judgment is flagged for independent verification.

---

## 11. What to verify and challenge (your task, Claude Code)

Do not take this document on faith. Independently research the following, compare against the repo's actual state, and report agreements, disagreements (with reasons + sources), and gaps.

1. **Re-read the actual repo** (stage prompts, ADRs, `CONSTITUTION.md`, the `aero/` code, handoffs) and confirm or refute this document's characterization: that the surrogate path is automotive-centric (Stages 09–10), that the fleet is five-solver, and that the `Surrogate` protocol + `CertificateOfValidity` are as reusable as §2 claims. Quote what you find.
2. **The automotive→airfoil non-transfer claim [JUDGMENT — load-bearing].** This is the single most consequential judgment here. Search for evidence on cross-regime transfer of neural-operator surrogates (automotive↔airfoil, attached↔separated, 2D↔3D). Does pretraining on a different flow regime help, hurt, or do nothing? If transfer is real, the §2 re-aim weakens. Report what the literature actually shows.
3. **Surrogate data scale for the operator's *actual* problem class [VERIFY].** Confirm the AirfRANS scarce-data (200) and GINO (~500) figures against the primary papers, then reason about whether ~150–500 holds for whatever the operator plugs in — especially 3D, unsteady, or separated cases, where the count likely rises. State your revised estimate and why.
4. **Surrogate architecture per problem class [VERIFY].** Don't assume Geo-FNO is universal. For a representative 3D-wing / unsteady-flapping / near-wall problem, which operator family (GINO, GAOT, AB-UPT, neural fields, MeshGraphNet) is appropriate, and what data/compute does each need? Check current (2025–2026) benchmarks.
5. **GPU pricing [VERIFY — time-sensitive].** Re-check live H100/A100/spot rates at the providers the operator can actually use (RunPod, Lambda, Vast.ai) and update §9.
6. **Solver-fidelity requirements [ESTABLISHED but VERIFY against primaries].** Confirm the riblet DNS resolution criteria (Δx⁺, Δy⁺, spanwise points), the minimal-span feasibility argument, and the FSI cost characterization against the cited papers (MacDonald 2017; Modesti 2021; Bechert 1997; García-Mayoral & Jiménez 2011; preCICE/Turek–Hron). Flag anything that doesn't hold for the fidelity the operator needs.
7. **V&V / UQ sufficiency [JUDGMENT].** Does the incremental, per-capability V&V approach (§5) actually clear a "thesis-grade output" bar? Propose the concrete benchmark menu and minimum UQ per capability. Push back if you think it's too thin or too heavy.
8. **Orchestration [JUDGMENT].** Re-evaluate Prefect vs Snakemake vs alternatives against the platform's real workload and the operator's separate `ai-orchestrator` repo. The §7 recommendation is a default, not a mandate.
9. **Agentic layer scope [JUDGMENT].** Decide whether even a thin agent wrapper is worth building before Layer 1 is solid, given the separate orchestrator repo. Re-check the latest agentic-CFD results.
10. **Define the output-validity bar [REQUIRED].** This document asserts the bar exists but does not pin it. Work out, concretely and with the operator, what "thesis-grade / publication-grade output" means operationally: validation tolerances vs reference data, minimum UQ (e.g., GCI on every reported quantity), provenance completeness, and reproducibility criteria. **This bar is the platform's actual product spec — treat producing it as a primary deliverable.**
11. **Disagree explicitly.** Wherever your independent findings contradict this document, say so plainly, cite sources, and reconcile against the repo and the operator's stated goals: general-purpose, pluggable, open-source, end-to-end observable, fully reproducible.

---

## 12. Caveats (treat these as the least-certain claims)

- **GPU pricing is volatile and source-dependent.** The §9 figures are 2026 snapshots; verify live before committing budget.
- **In-service riblet drag-reduction and agentic-CFD success figures are vendor / airline / benchmark-reported**, not fully independent. Lab maxima (~8–10%) come from peer-reviewed channel experiments; in-service numbers (~0.7–1% fuel burn) are lower and operator-reported. Agentic success rates (82–88%) are on curated benchmarks, not novel research geometry.
- **Per-case CPU/GPU-hour totals for academic riblet DNS are not always published explicitly**; the feasibility claim rests on the minimal-span cost-scaling argument plus modern single-GPU channel-flow benchmarks, not a single quoted core-hour figure.
- **The surrogate-transfer claim (§2) is an engineering-judgment synthesis** from distinct flow regimes and dataset designs, not a single published head-to-head benchmark. It is flagged for independent verification precisely because so much downstream advice depends on it.
- **This review assumes a single developer.** Several "defer" and "right-size" verdicts relax with additional contributors or funding.
- **Citations in this document originate from a prior research pass** and should be re-confirmed against the primary sources before being relied on in any written work.
