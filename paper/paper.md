---
title: 'aero-research-platform: provenance- and uncertainty-gated, CFD-verified aerodynamic shape optimization'
tags:
  - Python
  - computational fluid dynamics
  - aerodynamic shape optimization
  - verification and validation
  - uncertainty quantification
  - reproducibility
authors:
  - name: Louis Ernesto Schulte Moredo
    orcid: 0009-0004-8145-8319
    affiliation: 1
    corresponding: true
affiliations:
  - name: Independent Researcher
    index: 1
date: 12 October 2026
bibliography: paper.bib
---

# Summary

`aero-research-platform` is an open-source Python platform for computational-fluid-dynamics
(CFD) driven aerodynamic shape optimization. The CFD is the ground truth for every claim, and
the platform refuses to report a result that its own records do not support:
- every reported number carries a four-fold provenance tuple;
- every claimed improvement must exceed a combined 95 % uncertainty;
- every optimum is re-verified by CFD before it is reported;
- every exported result is a self-describing *result crate* that verifies away from the compute
  cluster.

Solvers (OpenFOAM [@weller1998], preCICE [@chourdakis2022]) run in Apptainer containers
[@kurtzer2017]. The platform core imports only the Python standard library, NumPy and pydantic.
Version 0.1.0 demonstrates the optimizer on a two-dimensional airfoil and the forward capability
on a rigid flapping wing. The optimizer has never been run on a flapping-wing case, and v0.1.0
makes no flapping-wing optimization claim.

# Statement of need

Shape optimization with CFD in the loop produces many candidate designs and a few attractive
numbers. Those numbers are easy to over-claim:
- a surrogate-predicted optimum may not survive a ground-truth solve;
- an improvement may be smaller than the discretization error of the meshes that produced it;
- best-of-N reporting inflates apparent gains;
- a result reproduced only on the cluster that produced it cannot be checked by a reviewer.

AI-assisted research workflows add selection bias and metric misuse to this list [@luo2025].

The platform is for researchers who need a reported aerodynamic improvement to be defensible.
It turns the usual guidance into constraints that code enforces:
- Grid-convergence error comes from the GCI [@roache1997; @celik2008].
- The validation-uncertainty framework is ASME V&V 20 [@asme2009]. A combined uncertainty
  $U_{95} = \sqrt{u_\mathrm{num}^2 + u_\mathrm{stat}^2 + u_\mathrm{input}^2}$ joins the numerical
  term with a batch-means statistical term for time-averaged quantities [@flyvbjerg1989], and a
  claimed delta must exceed $k\,U_{95}$ with $k=2$.
- Deltas between a baseline and a candidate are computed at matched numerics, so correlated
  errors cancel. The cancellation is measured, not assumed.

# State of the field

Mature open tools cover the building blocks:
- **Solvers:** OpenFOAM [@weller1998] and SU2 [@economon2016].
- **Adjoint optimization:** DAFoam [@he2020] and SU2.
- **Multidisciplinary design frameworks:** OpenMDAO [@gray2019].
- **Partitioned fluid–structure coupling:** preCICE [@chourdakis2022].
- **Black-box optimization:** Bayesian optimization [@jones1998].
- **Run tracking and packaging:** DVC and MLflow track runs. RO-Crate [@soilandreyes2022] and
  its Process Run Crate profile [@leo2024], with W3C PROV [@prov2013], package research outputs.

None of these makes an *invalid claim unconstructible*. An optimization framework will happily
report a delta inside its own error bar, and a provenance tool records what ran, not whether the
result is supported.

The platform therefore composes these tools rather than replacing them. It runs established
solvers, borrows the GCI and V&V 20 procedures, and emits standard RO-Crate and PROV metadata.
It builds only the missing integrity layer: typed claims, pre-registered gates, and portable,
self-verifying result records. Contributing that layer upstream would mean changing the contract
of each host project. Here it is the platform's whole purpose.

# Software design

**Strict schemas.** Every model is a pydantic model with `extra="forbid"`, frozen where
reasonable, and finite numbers only. A `ReportableResult` carries:
- its quantities and their $U_{95}$ envelope;
- its validation anchors;
- an optional `OptimizationResult`.

The `ImprovementClaim` validator raises a `SmallSignalError` unless the delta exceeds
$k\,U_{95}$. A hand-entered delta uncertainty cannot reach the thesis-grade tier, and a best-of-N
optimum needs a held-out CFD verification. The cost of this rigidity is real: four early records,
written before a validator existed, no longer load. They are refused, never "fixed".

**Provenance.** Each run records `(git_sha, dvc_input_hash, container_sif_sha256, config_hash)`.
The record states two known weaknesses:
- the DVC term is a remote-sync-state digest, not a content address;
- the container digest is looked up by file name, not re-hashed at launch.

**Pre-registration.** Gates, tolerances and bands are written into architecture decision records
before a campaign runs. They are never relaxed afterwards; a miss is reported as a NO-GO.

**Platform, not hub.** Solver, machine-learning and cloud dependencies sit behind optional
extras. A licence scan over the lockfile admits only GPL-3.0-compatible packages. Proprietary CUDA
wheels are confined to frozen-optional GPU extras.

**Result crates.** A crate is a directory or deterministic ZIP. It holds:
- the result;
- the exact configuration bytes whose SHA-256 *is* the recorded config hash;
- verbatim evidence;
- a typed validity context: claim tier, gated verdicts kept apart from reported diagnostics,
  applicability bounds, and the limitations the content makes mandatory;
- RO-Crate 1.3 / Process Run Crate and PROV-JSON projections.

The reader hashes every member before parsing and recomputes every derived value bit for bit,
under a sandbox that denies network and subprocess access. Continuous integration writes the
crates on one machine and verifies them on clean Linux, macOS and Windows runners holding only the
wheel, NumPy and pydantic. It compares every number against an independent oracle.

# Demonstrated scope and limitations at v0.1.0

The optimizer has never been run on a flapping-wing case, and v0.1.0 makes no flapping-wing
optimization claim. It is demonstrated on a NACA-4 camber-line airfoil (lift-to-drag ratio at
$Re = 5\times10^5$, angle of attack 4°, k-ω SST [@menter1994]). Its forward model has no
experiment anchor. \autoref{tab:gates} lists what the pre-registered gates decided; each row is
a published result crate.

: What the gates decided, by stage. \label{tab:gates}

| Stage | Result | Gate outcome |
|---|---|---|
| 12 | Oscillating-cylinder wake lock-in, $C_d = 1.993 \pm 0.079$ | Thesis-grade; lock-in anchor passed. The only thesis-grade record. |
| 14 | Rigid flapping wing vs. @wang2004 | The rotation-timing ordering is reproduced — a pre-registered, non-gated diagnostic. The gated mean lift misses by 45.7 % against a pre-registered ±25 % band — a documented NO-GO; the band was not relaxed. |
| 15 | CFD-in-the-loop airfoil optimization | NO-GO: the matched delta 24.66 did not exceed its own $U_{95}$ of 25.37. |
| 16 | Three-grid certification | NO-GO by one gate: observed order 0.465 vs. the 0.5 floor; shipped *validated*. |
| 17 | Surrogate-accelerated optimization | Delta vs. baseline 24.70 > $2U_{95}$ = 4.15 (two-grid GCI), capped at *validated*. The speed-up is a degenerate NO-GO. |

Each row has qualifications:
- **Stage 14.** The ordering is the rotation-timing lift signature of @dickinson1999. The
  advanced- and delayed-rotation mean lifts miss experiment by 38 % and 64 %.
  Overset wake-capture dissipation is the leading hypothesis for the shortfall.
- **Stage 17, the proposals.** They came from smoke-tier, in-loop retrained ensembles; every
  proposal was CFD-verified, and the validated surrogate certificate is a separate fit.
- **Stage 17, the optimum.** It exceeds the training corpus's best design by 0.035, far inside
  that quantity's $U_{95}$ of 7.03, and that margin is not claimed. Its "held-out" verification
  is a deterministic same-grid re-solve.

Beyond the table:
- **Stage 19.** A Turek–Hron FSI3 benchmark [@turek2006] verified the coupling.
- **Stage 20.** A flexible-flapping campaign against @heathcote2007 ended as a NO-GO on
  infrastructure, and flexible-flapping optimization is deferred.

The turbulent NASA TMR verification cases do not all pass: the flat-plate skin friction misses
by 12.6 % against a 5 % tolerance, which is not relaxed. So no result carries the production
tier. The project's own publication bar is therefore not met at v0.1.0: it needs a CFD-verified
optimization delta on a flapping case, and the turbulent canonical cases passing. Rigid-flapping
optimization, under a new pre-registration, is the next stage.

# Research impact statement

The author is an aerospace-engineering student focusing on CFD software. To date the author has
used the platform for testing, and plans to use it to build an understanding of flapping-wing
and other bio-inspired aerodynamics.

There are no external users to date. The reusable output of v0.1.0 is the set of gate-honest
records, NO-GOs included, published as verifiable result crates. A reader can check each crate's
numbers and limitations with three commands and no access to the original infrastructure.

# AI usage disclosure

<!-- AI-INVENTORY:START -->
*Generated by `scripts/ai_usage_inventory.py` from the post-stage handoffs and the commit trailers at `origin/main` (`83baa43225cd`).*

Every stage of the build (1–21) was carried out in Claude Code sessions (Anthropic) by an AI coding agent that wrote most of the code, tests and documentation, under the direction of the author. The models, as recorded in each stage's handoff, were: `claude-opus-4-7` (Stages 1–8); `claude-opus-4-8` (Stages 9–13, 15); `claude-fable-5` (Stages 14, 16–18); `claude-opus-5` (Stages 19–20); `claude-opus-5-5` (Stage 21). Of the 44 commits on `origin/main`, 27 carry a Claude `Co-Authored-By` trailer. The author directed every stage and accepted every architecture decision record and pre-registration. Merges and releases were the author's acts, or ran under the author's standing approval.
<!-- AI-INVENTORY:END -->

The author reviewed the AI-assisted work by splitting it into steps and reviewing the code before it was merged.

# Acknowledgements

This work received no external funding.

# References
