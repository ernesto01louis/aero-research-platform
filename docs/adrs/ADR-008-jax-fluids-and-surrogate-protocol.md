# ADR-008 — JAX-Fluids 2.x adapter, Surrogate protocol + Certificate of Validity, DrivAerNet++ quarantine, PyG choice

- **Status:** accepted
- **Date:** 2026-05-30
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 08)
- **Stage:** 08
- **Supersedes:** none. Builds on ADR-006 (Solver protocol), ADR-007 (GPU adapters + cost cap).

## Context and problem statement

Stage 08 brings two concurrent additions to the platform that share an ADR because they share constraints (PLATFORM-NOT-HUB, FAIL-LOUD, four-fold provenance, license posture):

1. **Differentiable CFD.** JAX-Fluids is the first solver in the stack whose forward run is end-to-end differentiable. It is a functional/pure-JAX codebase, structurally different from every prior adapter (imperative C++/Fortran behind an SSH-and-files boundary). It is the substrate Stage 13 needs for adjoint shape optimisation and learned closures.
2. **The Surrogate ↔ Agent contract.** Stage 09 (DoMINO) is the first production ML surrogate. Stage 14 (NeMo Agent Toolkit) is the first caller. Codifying a `Surrogate` protocol and `CertificateOfValidity` framework BEFORE the first production model exists is what keeps Principle 4 ("ML augments, never replaces, validated physics") structural rather than aspirational. The four CC-licensed public datasets (AhmedML, WindsorML, DrivAerML CC-BY-SA; DrivAerNet++ CC-BY-NC) all land in this stage so the loader contracts shake out under real data before Stage 09's training depends on them.

This ADR covers six discrete decisions. They are bundled because reversing any one of them implies revisiting at least one other.

## Decision drivers

- **Reproducibility (Principle 1; Invariant 3).** Every published number must trace to the four-tuple.
- **Compute fungibility (Principle 2).** The differentiability path must not bind the platform to a specific backend.
- **License hygiene (Principle 5; Invariant 5).** CC-BY-NC data must not co-mingle with CC-BY-SA / commercial-permissible artifacts.
- **No-premature-promotion of protocols.** ADR-006/007 promoted the `Solver` ABC twice based on repeated patterns across multiple adapters. Promoting again at one data point (the only differentiable adapter) is speculative.
- **Bus factor.** Three-layer defence on the CC-BY-NC boundary beats a single fragile guard, but a full import-hook taint system is heavier than this stage can audit.

## Considered options (one block per decision)

### D1 — JAX-Fluids version pin

1. **JAX-Fluids-v0.2.1 (latest 2.x-generation tag at 2026-05-30, git+url installed).** Upstream `tumaer/JAXFLUIDS` tags its second-generation rewrite as `JAX-Fluids-v0.2.x` even though the academic literature calls it "JAX-Fluids 2.0". v0.2.1 is the latest such tag.
2. **JAX-Fluids-v0.2.0.** One tag back; the prior tested release.
3. **Pin to a specific commit SHA on main.** Tightest reproducibility; loses human-readable version string in MLflow tags + ADR prose; needs justification why no tag was used.

### D2 — JAX-Fluids license posture

The stage prompt assumed GPL-3 and flagged "downstream implications". Investigation found upstream is **MIT-licensed** (`setup.py` `license="MIT"`, `LICENSE` in the repo confirms). Decision is to record the corrected posture: no copyleft propagation, no derivative-work obligations on platform code that imports `jaxfluids`. Cite Invariant 5; no aero code needs a license-compatibility shim.

### D3 — Differentiability seam shape

1. **Additive method on `JAXFluidsSolver` only.** `JAXFluidsSolver.run(case_dir, executor) → ResultHandle` goes through the SIF executor for parity with every other solver — same four-fold provenance path, same cost-cap-gated cloud execution. A separate additive method `differentiable_run(case, jax_grad_target) → JaxGradientResult` runs in-process against `jaxfluids`, bypasses the executor, does NOT enter the cost-cap ledger, and exposes primal + gradient pytree leaves as a typed mapping. The `Solver` ABC is NOT amended.
2. **Promote `differentiable_run` into the `Solver` ABC** with default `raise NotImplementedError`. Forces every adapter to consider its gradient story.
3. **Skip the adapter-level method entirely.** Expose a thin `aero.adapters.jax_fluids.gradients` module separate from the `Solver` boundary; the surrogate / optimisation layer calls it directly.

### D4 — DrivAerNet++ (CC-BY-NC) quarantine

1. **Loader-level guard only.** `DrivAerNetPlusPlusDataset(acknowledge_noncommercial=True)` raises if `False`. Certificate propagation is voluntary.
2. **Loader-level guard + structural separator subpackage + tainted-sample discriminated union** (three layers, defence-in-depth).
3. **Tainted-Dataset wrapper with full import-hook taint system.** Most rigorous, most code, hardest to audit.

### D5 — Certificate-of-Validity expiry policy

1. **6 months OR training-dataset DVC hash change**, whichever first.
2. **12 months OR hash change.** Lower revalidation overhead.
3. **No time expiry; hash change only.** Validity tied purely to inputs.
4. **3 months OR hash change.** Most conservative.

### D6 — Global GNN library choice (propagates to Stages 09–10)

1. **PyG / torch-geometric.** Aligns with PhysicsNeMo's PyG migration (X-MeshGraphNet, FIGConvNet). Larger maintainer base.
2. **DGL.** Better historical performance on heterogeneous graphs; misaligned with PhysicsNeMo direction.
3. **Defer; implement MGN baseline with raw torch.** Buys time, risks reinventing `MessagePassing` poorly.

## Decision outcome

- **D1:** Chose **option 1 — JAX-Fluids-v0.2.1**. Latest 2.x-generation tag; per operator approval 2026-05-30. Installed in the SIF and `aero[jax-fluids]` via `git+https://github.com/tumaer/JAXFLUIDS.git@JAX-Fluids-v0.2.1` (no PyPI package exists).
- **D2:** Recorded **MIT** posture. Stage-prompt's GPL-3 assumption is corrected; the platform incurs no copyleft obligation from this dependency.
- **D3:** Chose **option 1 — additive method on `JAXFluidsSolver` only**. ADR-006/007 already spent the protocol-promotion budget on patterns repeated across multiple adapters; promoting again at one data point would be speculative. `differentiable_run` is discoverable from the adapter (the natural place a Stage-13 reader looks) without leaking JAX-Fluids internals into the ABC.
- **D4:** Chose **option 2 — three-layer defence** (constructor guard + structural separator at `aero/surrogates/_common/loaders/non_commercial/` + `TaintedSample` Pydantic discriminated union that propagates `non_commercial=True` into any `CertificateOfValidity` the surrogate produces). Defence-in-depth without the audit weight of option 3.
- **D5:** Chose **option 1 — 6 months OR training-dataset DVC hash change**. Forces twice-yearly revalidation even on frozen datasets; the hash gate catches dataset drift between expiries. Per operator approval 2026-05-30.
- **D6:** Chose **option 1 — PyG / torch-geometric**. Per operator approval 2026-05-30; propagates to Stage 09 (FIGConvNet) and Stage 10 (X-MeshGraphNet).

### Consequences

- **Positive:**
  - The Solver ABC stays bit-stable through this stage; existing OpenFOAM/SU2/PyFR/NekRS code paths do not require a rebuild of mypy-strict guarantees.
  - The CC-BY-NC boundary is structural, greppable, and CI-enforced (`non-commercial-fence.yml` rejects any import from the quarantined subpackage that does not also produce `non_commercial=True` or carry the `# non-commercial: justified` pragma).
  - JAX-Fluids being MIT removes a perceived constraint on Stage 13's adjoint-optimisation layer.
  - The cert expiry policy is reachable by every Stage 14 agent invocation; surrogate "drift" cannot quietly accumulate.
- **Negative:**
  - `differentiable_run` on a single adapter is an asymmetry every code reader has to learn. ADR-008 lives prominently in `docs/adrs/` to mitigate.
  - The non-commercial fence depends on a CI grep + pragma convention; a contributor who bypasses the convention can route bytes through a different surrogate. Stage 14 layers a runtime check on top (`Surrogate.certificate().assert_current()` is called before `predict`).
  - Twice-yearly revalidation has a CI-time cost; Stage 13's multi-cloud cost router amortises it.
- **Neutral / followup work:**
  - When a SECOND differentiable adapter lands (Stage 10 Transolver gradient hook, or a `jax-cfd` follow-on), ADR-009-or-later promotes `differentiable_run` into the ABC and introduces a `JaxExecutor`. Until then, the asymmetry is documented.
  - Stage 09 may want to add a `cert_status="validated"` upgrade procedure (re-fit on full dataset + comparison against a held-out V&V case) — Stage-08 ships only `"smoke"`.
  - Stage 12 may want to add `applicability_envelope` constraints derived from the V&V harness's tolerance envelope; Stage-08 ships `re_range / mach_range / aoa_range_deg / geometry_class` as typed primitives.

## Pros and cons of considered options (decision-level highlights)

### D3 — alternatives

- **D3.2 (promote into ABC):** Good — forces every adapter to have an opinion on gradients. Bad — four of five adapters would `raise NotImplementedError`, a leaky abstraction that lies to V&V harness authors.
- **D3.3 (separate `gradients` module):** Good — keeps the ABC pristine. Bad — Stage 13's reader looking for "where does JAX-Fluids' gradient hook live?" has to know to look outside the adapter package.

### D4 — alternatives

- **D4.1 (loader guard only):** Good — minimal code. Bad — a fragile single-point of enforcement; legally consequential.
- **D4.3 (import-hook taint system):** Good — strictly correct. Bad — hard to audit, bus-factor concern, premature without a second non-commercial dataset to triangulate.

### D5 — alternatives

- **12 months:** Good — fewer revalidations. Bad — stretches trust window during solver/dataset churn.
- **3 months:** Good — strictest. Bad — burns CI/cluster time on revalidation; Stage 14 agent productionisation has to absorb the cost.
- **No time expiry:** Good — simplest. Bad — risks "permanent" surrogates whose physical envelope drifts silently.

### D6 — alternatives

- **DGL:** Good — flexible message-passing API. Bad — misaligned with PhysicsNeMo; would force a bridge layer at Stage 09 and a re-architecting at Stage 14 (PhysicsNeMo is PyG-native).
- **Defer:** Good — buys time. Bad — Stage-08's MeshGraphNet baseline would lack a message-passing primitive and would risk reinventing `MessagePassing` poorly.

## Links

- Project brief: `00-CONTEXT-project-brief.md`
- Stage prompt: `docs/handoff-bundle/STAGE-08-jax-fluids-and-surrogate-plumbing.md` (operator-pasted)
- Related ADR: ADR-006 (Solver protocol), ADR-007 (GPU adapters + cost cap)
- Related handoff: `docs/handoffs/STAGE-07-pyfr-and-nekrs-adapters-DONE-2026-05-20.md`
- External:
  - JAX-Fluids upstream: https://github.com/tumaer/JAXFLUIDS (tag JAX-Fluids-v0.2.1; MIT)
  - Bezgin, Buhendwa, Adams 2023 — *JAX-Fluids: A fully-differentiable high-order computational fluid dynamics solver for compressible two-phase flows*. CPC.
  - PyG / torch-geometric: https://github.com/pyg-team/pytorch_geometric
  - AhmedML dataset (CC-BY-SA), WindsorML (CC-BY-SA), DrivAerML (CC-BY-SA), DrivAerNet++ (CC-BY-NC) — references at `data/datasets/*/reference.md`
