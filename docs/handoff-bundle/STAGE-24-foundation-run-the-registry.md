# STAGE 24 — Foundation III: Run the Registry (ADR-051)

> **Stage 23 closed the second foundation stage** (`v0.1.2`, ADR-051 D4). Since then, the four-tuple
> means what CONSTITUTION Invariant 3 says, as amended at Stage 23:
> - `dvc_input_hash` is the content address of the `.dvc` inputs a case **declares**
>   (`declared-dvc-pointers-md5/v1`, ADR-052).
> - `container_sif_sha256` is checked against the SIF on the solve host before **every** launch
>   (`sif-sha256-verified-at-launch/v1`, ADR-053).
> - Every tuple names its schemes in its tags, and a run without them is pre-Stage-23.
> - A hosted runner reproduces one Blasius number from the cluster's own container (ADR-050).
>
> Read its handoff first: `docs/handoffs/STAGE-23-foundation-provenance-DONE-2026-10-21.md`.
>
> **This stage runs every active-stack registered case through the registry path, under those
> semantics** (ADR-051 row 24). That means the 9 with no run, the 4 failing and the 7 passing,
> re-confirmed. Each result is triaged: pass, or fail with a written first diagnosis. This stage
> measures and diagnoses. Stage 25 takes the turbulent canonical cases (the TMR flat plate, NACA 0012
> verification and the 2D bump) to a pass or a demonstrated root cause.
>
> **This is campaign compute** (ADR-051 D3): cluster CPU only, on the platform's own LXCs, with no
> cloud spend. **A compute plan is approved by the operator before any run.** One case alone is long:
> Stage 19's FSI3 took 20.3 h. A tolerance is a contract. Stage 20 stays closed. Flexible flapping
> stays deferred (ADR-046 S4/S5).

## BEFORE YOU START — READ

1. `CLAUDE.md` and `.aero-stage`. Set it to `24` in the first commit, with the Dependabot prefix
   `ci(stage-24)`; `tests/unit/test_workflow_hygiene.py` requires the two to agree.
2. The Stage-23 handoff: §2 (decisions), §3 (deviations), §6 (gotchas) and §7 (open items: the
   operator's outstanding actions, including the MinIO key rotation).
3. **ADR-051** (row 24, D2 and D3), **ADR-052** (the declared inputs and their goldens),
   **ADR-053** (the launch guard), **ADR-050** (the hosted check), **ADR-005** (the V&V harness,
   per-stack verdict) and CONSTITUTION Invariant 3 (amended at Stage 23).
4. The code that runs and reads the registry:
   - `aero vv run --case` (`aero/cli.py`, `aero/vv/_base.py` `BenchmarkRunner`);
   - `aero/vv/stacks.py` (the 25 cases and their stacks) and `aero/vv/report.py` (the gate);
   - `scripts/provenance_readback.py`: the independent read-back of a run, from git alone.

## Why this stage

At Stage 22's close the OpenFOAM stack was RED: 7 pass, 4 fail, 9 missing. Every one of those runs
was recorded under the weak semantics: a repository-wide `dvc status` digest and a basename lookup.
Optimizing over that registry would build on numbers whose inputs and containers nobody can name.
This stage replaces each row with a run whose four terms are content addresses, read back.

## Decisions to put to the operator at stage open (not yet decided)

| # | Question | Notes |
|---|---|---|
| D1 | Does the gate count only runs with the v1 schemes? | `aero vv report --latest` reads the newest run per case and stack, whatever its schemes. A strict filter would turn the 7 pre-Stage-23 passes into `missing` until they are re-run, which this stage does anyway. The alternative is display-only: show the scheme beside each row |
| D2 | The registry path for the coupled and external-geometry cases | `turek_hron_fsi3` must run through `aero vv run --case` (the Stage-19 driver is refused until ported), but the CLI's executor ceiling is 30 min (`LocalSSHExecutor` default) and FSI3 needs about 20 h: a detached long-job path is needed. The `aero vv run` path for the Turek-Hron CFD pair is single-shot, with no mesh ladder (promoting the ladder is ledgered): run it single-shot, or promote the ladder first |
| D3 | The compute plan (ADR-051 D3) | For each case: the wall-time estimate from its recorded runs (read MLflow, read-only), the `run_long.sh` session, reap and timeout plan, and the order. **Both `vv` runners and every solve share the one aero-build host:** never start two long solves at once (Stage 23 lost a FULL run to that). Include the total, and which cases run overnight |
| D4 | What a "first diagnosis" is, and where it lives | per failing case: the measured vs reference values, the tolerance, the log evidence, and a ranked hypothesis list. Never relabel; never relax; never write a crate under `data/vv/` |
| D5 | Do PR-branch CI runs count as registry evidence? | they log to the same experiment (`ci_event` tag); D1's filter may need to exclude them |
| D6 | `dataset_hash` (ADR-052 left it on the sync-state meaning) | it backs the Stage-17 certificate's data gate; the certificate expires **2027-01-20**. Its ADR is due before the renewal, and may be this stage's or Stage 25's |

## Deliverables

1. **Bookkeeping (first commit):** `.aero-stage` → `24`; the Dependabot prefix → `ci(stage-24)`.
   Open a `status: partial` handoff `docs/handoffs/STAGE-24-foundation-run-the-registry-DONE-YYYY-MM-DD.md`
   with `stage_tag: v0.1.3`, `next_stage: 25` and
   `next_stage_name: "Stage 25 — Foundation IV: The Turbulent Canonical Cases"`, and regenerate the
   README.
2. **The compute plan**, approved by the operator before the first run (D3), recorded in the
   handoff.
3. **Every active-stack registered case runs once** through the registry path under the v1 schemes
   (D2 decides the coupled path). Each run is read back with `scripts/provenance_readback.py`
   (`--mirror`): both v1 schemes, the declared inputs (ADR-052's table), and the SIF digest
   verified at every launch.
4. **The triage:** per case, `pass`, or `fail` with a written first diagnosis (D4). The handoff
   records the per-case table, cross-checked against `scripts/vv_report_crosscheck.py`.
5. **The gate change, if D1 chooses one**, with its tests.
6. **The close: `v0.1.3`** through the release PR, as at Stage 23; the operator cuts the tag.

## GO / NO-GO

- **GO requires:**
  - every active-stack case has a v1-scheme run that was read back, with a triage row;
  - the compute plan was approved before the first run;
  - no tolerance moved, and no case became `pass` without a passing run;
  - all required CI green.
- **NO-GO** leaves the handoff `partial` and names the cases still unmeasured. "Not yet" is
  acceptable; a case reported as measured that was not is not.

## Infra, conventions and inherited notes (from Stage 23)

- **Provenance since Stage 23:**
  - every case class declares `dvc_inputs`, and `compute_provenance(..., dvc_inputs=...)` is
    required;
  - read DVC-tracked files only through `aero.provenance.dvc_inputs.read_declared_input`;
  - `Solver.prepare(spec, *, provenance)` binds the tuple to the case, and every launch is pinned
    from it;
  - a refused launch is exit 86 and raises `ProvenanceError`, never a solver failure;
  - a declared pointer and `containers/SHA256SUMS` must equal `HEAD`'s, even for `--allow-dirty`.
- **The guard's cost per launch** (measured over NFS): about 2 s for `openfoam-esi.sif`, 4 s for
  `precice-fsi.sif`, and 19 s for `pyfr.sif`. Budget it into multi-launch cases.
- **Still legacy:** `ReportableResult`, `OptimizationResult`, the corpus and crate format v1 accept
  only the legacy tuple until a crate-v2 ADR, so no new-semantics result travels as a crate yet.
- **Refused, exit 4 (ledgered):** RunPod solver paths, `aero surrogate train`, the historical stage
  drivers (ported: `stage11_moving_vv`, `stage18_turek_hron` and `hosted_repro`), the Stage-20
  numerics screen, and the hg2007 restart.
- **One host for everything:** both `vv` runners and every solve run on aero-build. The V&V
  executor ceiling is 45 min (`cylinder_strouhal_re100` takes about 28 min alone). Long solves go
  through `scripts/run_long.sh` with REAP on; never use `run_long.sh wait`.
- **CI and merging:**
  - 12 required contexts; strict protection; one merge per main movement.
  - Squash merges break stacked branches: merge `main` in, and reword the merge commit to a
    Conventional Commit.
  - Headers are ≤ 100 characters, checked before every push.
  - Self-hosted V&V workflows run only for PRs into `main`, so stacked PRs cost no cluster time.
  - **Merging, tagging and publishing a Release are operator acts** (SECURITY.md); the auto-mode
    classifier refused the agent's `gh pr merge` and `git tag`.
- **Hard don'ts** (unchanged):
  - never create the two ADR-045 records, and never fill a B-sentinel;
  - keep `stage-20-evidence-2026-09-20`, and never write a crate under `data/vv/`;
  - PR #21 (`aero-nas` → `192.168.2.60`) stays "leave unless the operator asks";
    `192.168.2.100:9000` no longer answers;
  - never print `.dvc/config.local`, Vault output or the `AERO_*` secrets.

## POST-STAGE HANDOFF (mandatory)

One file, kept from the first commit to the close. Emphasise:
- the approved compute plan, and the measured wall time of every run against its estimate;
- the per-case table: status, run id, both schemes, the read-back result, and for each failure its
  first diagnosis;
- the operator's answers to D1–D6;
- anything Stage 25 (the turbulent canonical cases, ADR-051 row 25) must know.

Author the Stage-25 prompt in `docs/handoff-bundle/` before closing.
