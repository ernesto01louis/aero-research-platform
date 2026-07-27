# ADR-035 — preCICE coupling contract: adapter shape, version pins, and container strategy

- **Status:** accepted
- **Date:** 2026-07-27
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 19)
- **Stage:** 19
- **Supersedes:** —

## Context and problem statement

ADR-016 chose the FSI strategy — verify coupling on the *supported* upstream Turek-Hron
tutorial, and build CalculiX separately as the Stage-20 application solid solver — but
left the execution open: `aero/adapters/precice/` and `aero/vv/fsi/` were `.gitkeep`
stubs and `aero[precice]` was an empty list. Stage 19 executes it, and four decisions
have to be recorded before any campaign runs, because each one can silently corrupt the
result rather than loudly break it:

1. **What shape does a two-participant co-simulation take** in a platform whose solver
   contract assumes one solver per run? Nothing in the repo launches two long-lived
   processes; `LocalSSHExecutor` blocks until its single detached job finishes.
2. **Which versions?** preCICE couples a C++ library, Python bindings, an OpenFOAM
   adapter compiled against a specific OpenFOAM, and a solid solver. A mismatch between
   the bindings and the library is an ABI problem: it does not announce itself.
   (Hard Rule 8.)
3. **One container or two?** The stage prompt asks for the choice explicitly. The
   four-fold provenance tuple carries exactly one `container_sif_sha256`.
4. **Licences.** CalculiX is GPL-2+, which is not on Invariant 5's named list.

## Decision drivers

- **Run the supported tutorial, verbatim.** The value of this stage is that the coupling
  evidence is *external*. Every byte we change weakens it, so changes must be few,
  declared, and mechanically enforced.
- **Fail loud, not late.** The realistic failure modes here — an ABI mismatch, a
  non-converged coupling, a shadowed adapter library, a partial watch-point read — all
  produce plausible numbers rather than crashes.
- **Do not widen a load-bearing contract for one stage.** Both `Solver`/`SolverProtocol`
  and `ProvenanceTuple` are consumed everywhere; a change to either for the benefit of a
  single adapter is a poor trade.
- **Pin from evidence, not judgement, where evidence exists.**

## Considered options

1. **Additive sibling adapter + one combined SIF for the gated run.** `PreciceCoupledSolver`
   subclasses the existing `Solver`; a single image carries OpenFOAM, preCICE, the
   adapter and the Nutils solid; participants are launched concurrently by a generated
   supervisor script inside one detached job.
2. **Two SIFs (fluid, solid) + a provenance schema change** so the tuple can carry a list
   of container digests.
3. **Amend the `Solver` ABC / introduce a `CoupledSolver` protocol** in
   `aero/adapters/_base.py`, and extend the `Executor` protocol with non-blocking
   submission so participants can be launched as separate jobs.

## Decision outcome

Chose **Option 1** because a coupled run genuinely fits the existing lifecycle once the
`CaseDir` is taken to be the tutorial root, and the two contracts that would otherwise
have to change are the two most widely consumed models in the repo.

**The adapter shape.** `PreciceCoupledSolver(Solver)` with `prepare -> mesh -> run ->
load` mapped as: materialize the digest-verified pinned tutorial and assert its
configuration; `blockMesh` the fluid participant; launch all participants concurrently;
read the flag-tip watch-point into a `TimeHistory`. `aero/adapters/_base.py` is
**untouched**. Two Stage-07 promotions are what make it fit — `SolveResult.cd`/`.cl` are
`float | None` and `scalars: dict[str, float]` exists — which is the same reasoning
ADR-008 §D3 used to give JAX-Fluids' differentiable path a sibling method rather than
widening the base class. `wall_distribution` raises `NotImplementedError`: a partitioned
FSI run has no single wall distribution, and returning an empty one would be a silent
fallback.

**Concurrency without touching `Executor`.** The payload is made concurrent instead of
the executor. `aero/adapters/precice/launcher.py` renders a supervisor script that
backgrounds every participant, polls them, takes the coupling down if one dies, enforces
the wall-clock ceiling with SIGTERM → grace → SIGKILL, and **always** writes
`coupled-status.json` recording per-participant exit codes and a `stopped_by`
discriminator. The executor still sees one command with one exit code, `run_long.sh`'s
sentinels still mean what they meant, and "we hit the ceiling" becomes a recorded
outcome rather than an inference from a truncated log. The executor's poll timeout is set
*above* the supervisor's ceiling so the supervisor, not the poller, is the authority —
closing the known trap where `LocalSSHExecutor`'s default long timeout silently fails a
long solve that is in fact still running.

**Version pins (Hard Rule 8).** Taken from upstream's own attested
`tools/tests/reference_versions.yaml` at the pinned tutorials commit — the file preCICE's
CI uses to generate its reference results — rather than from our judgement:

| Component | Pin | Source of the pin |
|---|---|---|
| `precice/tutorials` | `cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e` (branch `develop`) | the FSI participants and `reference-results/` exist only on `develop` |
| preCICE | **v3.4.1**, `libprecice3_3.4.1_noble.deb`, sha256 `3a36a402…be888` | upstream `PRECICE_REF` |
| pyprecice | **3.4.0** | upstream `PYTHON_BINDINGS_REF` |
| openfoam-adapter | **`2c3062ce941915616ac763371805c57e15e02466`** | upstream `OPENFOAM_ADAPTER_REF` |
| OpenFOAM | **ESI v2412**, image digest `sha256:1ba02114…41b50` | the same digest as `openfoam-esi.sif` |
| Nutils stack | nutils 9.2, numpy 1.26.4, meshio 5.3.5, gmsh 4.15.2 | upstream `solid-nutils/requirements-reference.txt` |
| CalculiX | **2.20** + calculix-adapter **v2.20.1** | upstream `CALCULIX_VERSION` / `CALCULIX_ADAPTER_REF` |

The adapter pin deserves a note: its last *tagged* release (v1.3.1, 2024-06) predates
OpenFOAM v2412 and `master` has not moved since, so a tag would not build against our
base. The pinned `develop` commit is the one upstream's own container recipe builds
against OpenFOAM v2412, which is stronger evidence than a version-table lookup.
`aero.adapters.precice.PINNED_*` constants, the `aero[precice]` extra and the container
recipe are checked for agreement by a required-CI unit test.

**Containers.** `precice-fsi.sif` — OpenFOAM v2412 (from the *same* base image digest as
the platform's validated `openfoam-esi.sif`, so `pimpleFoam` is byte-identical) + preCICE
3.4.1 from the official `.deb` + the openfoam-adapter built at the pinned commit + an
isolated venv at `/opt/aero/solid-venv` holding the Nutils stack. `calculix-precice.sif`
is separate and carries CalculiX + its adapter. Built by the established two-step
rootless-buildah → `apptainer build` from `oci-archive` path, because the Apptainer build
sandbox in the unprivileged `aero-build` LXC cannot open sockets.

`CoupledCaseSpec` **structurally forbids** a gated run from spanning more than one SIF, so
the provenance tuple stays single-valued by construction rather than by convention. The
CalculiX smoke is inherently two-container and is therefore declared `gated=False`; its
extra digests ride in `config_hash`. The manifest header's reserved name
`precice-distribution.sif` is retired in favour of the two actual names.

Three build details that are correctness, not packaging:

- the adapter is installed into `$FOAM_LIBBIN`, not the default `$FOAM_USER_LIBBIN`, and
  every participant runs with `--no-home`. Apptainer bind-mounts the host `$HOME` by
  default, so a host `~/OpenFOAM/` tree would shadow the image's copy and
  `controlDict`'s `libs (...)` line would fail to load the adapter **at run time only**;
- the Nutils stack needs `numpy<2` while the platform core requires `numpy>=2`, so it is
  confined to its own venv inside the image and never enters `aero[precice]`;
- upstream's `run.sh` builds a venv from the network unless `PRECICE_TUTORIALS_NO_VENV`
  is set. Setting it lets us keep upstream's entry point verbatim while using the
  pre-baked, network-free stack.

**What the `aero[precice]` extra is for — honestly.** Nothing host-side imports
`pyprecice`: both participants are upstream code inside the SIF, and everything
`aero/adapters/precice/` does on the host is stdlib file parsing. Rather than ship a
decorative extra, it has exactly one consumer — `solverdummy.py`, a two-participant
dummy executed *inside* the SIF as the infrastructure pre-flight, which proves in seconds
that `apptainer exec` works, `MPI_Init` succeeds in the unprivileged LXC, socket m2n
connects between processes, `--no-home` breaks nothing, and the supervisor logic is
correct — before committing to a multi-hour campaign. It is also the declared path for a
future in-process participant. No CI job installs it (`pyprecice` is sdist-only and needs
the preCICE and MPI headers present).

**Licence dispositions (Invariant 5).** preCICE LGPL-3.0 and `precice/tutorials` LGPL-3.0
— on the list. Nutils MIT and pyprecice LGPL-3.0 — permissive/on the list. **CalculiX is
GPL-2+**, which the Invariant's line ("GPL-3 / LGPL-3 / Apache-2.0 / BSD-3") does not
name. Following ADR-033 §6's reading that the list states a *posture* — copyleft-friendly,
no proprietary blobs — rather than an exhaustive whitelist, GPL-2-or-later is accepted:
it is free software, its "or later" clause makes it GPL-3-compatible, and it ships as a
separate container invoked as a subprocess, not linked into `aero/`. Recorded explicitly
so a future reader does not have to re-derive it.

### Consequences

**Positive.** The two most widely consumed contracts in the repo are unchanged, so no
other adapter or stage is disturbed. The coupled run keeps the ordinary four-fold
provenance shape. Every version in the stack is the combination upstream itself tests.
The pre-flight can fail in seconds rather than hours. The supervisor makes budget
exhaustion a first-class recorded outcome, which is what lets a budget NO-GO be honest.

**Negative (honest limits).** A single combined image mixes fluid and solid dependency
stacks; that is contained by the separate venv but it is not elegant, and it means a
Nutils bump rebuilds an OpenFOAM-bearing image. The supervisor is generated bash — tested
by executing all three of its stop paths against stub participants, but bash nonetheless.
`PreciceCoupledSolver.wall_distribution` raising means it satisfies `SolverProtocol`
structurally while not being usable everywhere a solver is; that is honest but it is a
sharp edge. And the `precice` extra is, for this stage, exercised only inside a container —
its value is real but narrow, and the pyproject comment says so rather than implying more.

**Neutral / followup.** A second coupled adapter, or an in-process participant, is the
data point that would justify promoting a `CoupledSolver` protocol into
`aero/adapters/_base.py` — the same "wait for the second case" rule ADR-006/007 applied.
If a future gated run genuinely needs two containers, `ProvenanceTuple` needs a decision
of its own; this ADR deliberately does not pre-empt it.

## Pros and cons of considered options

**Option 1 — additive sibling + one combined SIF (chosen)**
- Good: no change to `Solver`, `SolverProtocol`, `Executor` or `ProvenanceTuple`.
- Good: single container digest keeps the four-tuple honest without a schema change.
- Good: `pimpleFoam` provably identical to the platform's validated OpenFOAM.
- Bad: one image carrying two dependency stacks; larger, and coupled rebuilds.

**Option 2 — two SIFs + provenance schema change**
- Good: cleaner separation; a solid-solver swap does not rebuild the fluid image.
- Bad: changes `ProvenanceTuple`, which every stage since 04 depends on, for one stage.
- Bad: adds socket-m2n-across-two-containers as an unknown to the run that produces the
  claim (it is exercised by the non-gated CalculiX smoke instead).

**Option 3 — amend the ABC and the Executor protocol**
- Good: the most general expression of co-simulation.
- Bad: pushes optional, usually-`None` structure onto four adapters that gain nothing.
- Bad: a non-blocking `Executor.run` changes the semantics every existing caller relies
  on, on the evidence of a single use case.

## Links

- ADR-016 (FSI structural-solver strategy — the decision this executes), ADR-036 (the
  pre-registered FSI3 gate block), ADR-008 §D3 (additive-sibling precedent), ADR-033 §6
  (licence-posture reading), ADR-012 (non-interactive SIF signing), ADR-019 (the
  post-processing toolkit `limit_cycle` extends).
- `data/references/fsi/turek_hron_fsi3/reference.md` — pin provenance and the three
  cross-checks (blockMeshDict digest continuity with Stage 18; physics files identical to
  upstream's reference-generation commit; the only `controlDict` difference is a deleted
  comment).
- Upstream: `precice/tutorials` `tools/tests/reference_versions.yaml`; preCICE v3.4.1
  release; `precice/openfoam-adapter`; `precice/calculix-adapter` v2.20.1.
