# ADR-053 — `container_sif_sha256` is checked against the bytes that launch: a guard before every `apptainer exec`

- **Status:** **accepted** — the operator decided D3 on 2026-10-21 at the Stage-23 plan review
  ("Guard before every launch") and **accepted this text on 2026-10-21** ("Accept as written"),
  after its adversarial review; the acceptance is recorded by the commit that lands it. It fits
  CONSTITUTION Invariant 3 item 3 as written ("SHA256 of the Apptainer SIF that ran the job, pulled
  from `containers/SHA256SUMS`"), so it needs no amendment.
- **Date:** 2026-10-21
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 23)
- **Stage:** 23 (Foundation II, ADR-051 row 23)
- **Supersedes:** none
- **Amends on acceptance:** ADR-004 term 3 (`container_sif_sha256`), for runs that carry the scheme
  `sif-sha256-verified-at-launch/v1`. ADR-004's decision text is not edited; on acceptance a dated
  amendment note under its Status line (the ADR-046 pattern) points term 3 here.
- **Closes:** ADR-049 O-08 (and, with ADR-052, H-33's documented weakness for new runs).

## Context and problem statement

`container_sif_sha256` (`aero/provenance/four_fold.py:250-264` at `0c96e45`) is:

```python
def container_sif_sha256(repo_root: Path, container_sif: Path | str) -> str:
    name = Path(container_sif).name
    sums = repo_root / "containers" / "SHA256SUMS"
    ...
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == name:
            return parts[0]
    raise ProvenanceError(f"no SHA256 entry for '{name}' in {sums}")
```

It reads the submitting checkout's `containers/SHA256SUMS` and returns the first two-token line whose
second token is the basename. **The SIF is never opened.** Nothing ties the recorded digest to the file
`apptainer` then executes. Measured on 2026-10-21:

- all 2502 MLflow runs carry `c9d7f329…`, the `openfoam-esi.sif` entry, looked up by name;
- the live `openfoam-esi.sif` (455.6 MB) hashes to that entry in 2.19 s on aero-build, and `pyfr.sif`
  (4.25 GB) to its own in 19.1 s: the record is consistent, but it was never measured at launch;
- the SIFs sit on the TrueNAS NFS export (`/opt/aero/containers` → `/mnt/aero/containers`), writable
  by root on the Proxmox host and on TrueNAS;
- two concrete O-08 failures exist already:
  - `aero run --solver su2|pyfr|nekrs|jax-fluids` records the OpenFOAM digest while the adapter runs
    its own SIF (`aero/cli.py:450-453`; no such run was ever logged to MLflow);
  - `calculix-precice.sif` was rebuilt under the same name (`4ca47da2…` → `ac0805d6…`,
    `containers/SHA256SUMS:13-17`), the case a basename lookup cannot see;
- all 13 SIFs carry a PGP signature block, but nothing verifies it at launch; and re-signing changes the
  file's sha256 (`containers/SHA256SUMS:28-31`), contrary to ADR-012:59-60's unverified expectation
  ("Signing does not change the squashfs SHA256 (verify on-box; if it does, SHA256SUMS churns)").

Every adapter launch goes through one seam, `build_apptainer_exec` (`aero/adapters/_base.py:63`;
19 call sites in `aero/` and `scripts/`, plus 7 in tests), including the preCICE participants inside
`run-coupled.sh`, decompose, the robust-mesh
`checkMesh` and the Stage-16/20 scripts. An executor-level hook would not see the participants (the
executor only receives `bash run-coupled.sh`), and a per-run probe would leave the window between the
first and the last launch open for the whole run (FSI3 ran 20.3 h).

## Decision drivers

- **Invariant 3's meaning:** the digest is that of the SIF **that ran the job**.
- **Every launch, not one:** mesh, solve, `checkMesh`, each coupled participant, each relaunch.
- **Bind the record to the launch by construction:** the expected digest comes from the run's own tuple,
  never re-derived by the adapter from its own path, so a mislabelled run is refused, not "verified".
- **Fail loud, and never as physics:** a refused launch is a provenance error, never a solver failure
  or a logged `fail`.
- **No stale digest:** no cache whose key can survive a changed file.

## Considered options

1. **A guard before every launch** in `build_apptainer_exec` — chosen.
2. **A probe before and after the run** through the executor: no change to the command bytes, but
   launches in between and outside the runner are not checked.
3. **Probe plus guard:** the same guarantee as the guard alone, with earlier attribution and more code.
4. **A re-hash on the control host** when the tuple is computed: not on the solve host, its window spans
   the run, and it does not bind the executed file.

## Decision outcome

Chose **option 1** (operator, 2026-10-21).

- **The pin.** `build_apptainer_exec(..., expected: SifPin)` takes a required `SifPin(path, sha256)`
  with no default. The pin is built from the run's `ProvenanceTupleV2` (ADR-052): the container of
  record (`container_sif_name`, `container_sif_sha256`) or a roster member. Before any command is built,
  the adapter's SIF basename must be one the tuple names; otherwise the run is refused. So
  `aero run --solver su2` with the OpenFOAM SIF configured is refused, where a re-derived digest would
  have passed. `containers/SHA256SUMS` must equal `HEAD`'s even under `--allow-dirty`, as declared
  pointers must (ADR-052 D1), or the recorded digest would be in no committed `SHA256SUMS`.
- **The guard.** Every command is prefixed, on the solve host and in the same shell, with:

  ```sh
  { printf '%s  %s\n' HEX PATH | sha256sum --check --status - \
      || { printf 'AERO-SIF-REFUSED expected=%s path=%s\n' HEX PATH >&2; exit 86; }; } \
    && printf 'AERO-SIF-VERIFIED sha256=%s path=%s\n' HEX PATH >&2 && apptainer exec ... PATH ...
  ```

  `HEX` must match `^[0-9a-f]{64}$`; `PATH` may not contain a newline, is shell-quoted, and is
  the same bytes as the SIF argument of the `apptainer exec` it guards. `HEX` and `PATH` are `printf`
  arguments, never part of a format string (a quoted path with a space, or a `%`, would corrupt the
  line). Callers run the command in a shell, never prefix it with another command word (`timeout`,
  `env`, `nohup`: `{` is reserved only at the start of a command), and group it before appending a
  redirect, as `run-coupled.sh` does (`aero/adapters/precice/launcher.py:410`). The guard
  never contains the literal `apptainer exec ` before the real one: the three sites that inject
  `--no-home` by rewriting that first occurrence (`aero/adapters/precice/launcher.py:369`,
  `aero/adapters/precice/solver.py:564`, `scripts/stage20_numerics_screen.py:310`) are first replaced
  by a structural `no_home` flag whose output is byte-identical.
- **The sentinel.** Exit 86 with an `AERO-SIF-REFUSED` line is mapped to `ProvenanceError` by
  `raise_if_container_refused(result)` in every adapter failure path, in every caller that runs a
  built command itself (the robust-mesh ladder's `checkMesh`,
  `aero/adapters/openfoam/robust_mesh.py:144-151`) and in the V&V runner, before any retry, fallback
  or next-rung decision. The line is in `ExecResult.stderr` for a synchronous launch and in
  `ExecResult.stdout` for a detached one (`scripts/run_long.sh:99` merges the streams;
  `aero/orchestration/local_ssh.py:286-290`). The preCICE supervisor exits 86 if any participant did,
  ahead of its first-nonzero rule (`aero/adapters/precice/launcher.py:522-525`), and that participant's
  line is in its log in the case directory (`launcher.py:410`). A refused launch is never read as a
  solver failure and is never logged.
- **The record.** The scheme `sif-sha256-verified-at-launch/v1` (ADR-052) is written only for a run
  whose every launch went through the guard: the binding counts guarded launches, and the runner
  refuses to log the v1 scheme with zero. Each launch's `AERO-SIF-VERIFIED` line is in
  that launch's captured output: `ExecResult.stderr` for a synchronous launch (returned over SSH, not
  written on the solve host), the job's `~/.aero-jobs/<session>/output.log` for a detached one, and the
  participant log in the case directory for a coupled one.
- **No cache.** Every launch re-hashes. Measured over NFS on aero-build: 2.19 s for
  `openfoam-esi.sif` (455.6 MB) and 19.1 s for `pyfr.sif` (4.25 GB); by size, about 4 s for
  `precice-fsi.sif` (832 MB) and up to about 70 s for the 15 GB `physicsnemo.sif` (estimates). A cache
  keyed on file metadata can
  be stale under NFS attribute caching.
- **Refused paths** (fail loud, ledgered): RunPod solver paths (no SIF exists on the pod; reviving them
  needs an OCI pull-by-digest scheme); the DoMINO hand launch (`aero/cli.py:292`, frozen); runs that
  launch no SIF but would record one (the surrogate smoke CLI, `JaxFluidsSolver.differentiable_run`).
  `scripts/stage14_lev_snapshots.py:41` post-processes an existing case over raw SSH and records no
  run; a hygiene test allowlists it by name.
- **Hardening that rides along.** The `SHA256SUMS` parser skips `#` and blank lines, requires a 64-hex
  digest, refuses duplicate names and raises `ProvenanceError` (a two-token comment line that names a
  SIF would otherwise return `#` as its digest).

**The guarantee, verbatim.** For every `apptainer exec` it issues for a recorded run, the platform
first reads the whole SIF file at the launch path on the solve host and compares its sha256 with the
digest this run's tuple names for that basename; on a mismatch, or on a basename the tuple does not
name, the launch stops before apptainer starts. This proves the file held the recorded bytes when it
was checked. It does not prove that apptainer then read the same bytes: a file rewritten, replaced or
re-pointed at that path after the hash read begins (seconds on the active stack, about a minute for
the largest SIF) and before apptainer has read the image, which may last the whole launch, is not
detected. Root on the Proxmox host and on TrueNAS can write the NFS export, including the
`run-coupled.sh` that carries the expected digest, so the guard is no defence against them. The digest
covers the whole file, signature block included, so re-signing or rebuilding a SIF changes it, and a
changed SIF must be recorded under a new name in `SHA256SUMS`. The signature itself is not verified at
launch.

**Invariant 3.** Item 3 fits as written: the recorded digest is still the `SHA256SUMS` entry, and the
file each launch starts is now checked against it on the solve host (up to the residual window above).
The amendment PR of ADR-052 updates the Enforcement paragraph to name the guard (a clarification, as
ADR-038's was).

## Consequences

- **Positive:**
  - the file each launch starts is checked against the recorded digest, coupled participants and
    relaunches included, up to the residual window stated above;
  - the existing `aero run --solver` mislabel and the same-name-rebuild case are refused;
  - each launch leaves a verification line in its captured output (see The record), so the end-to-end
    proof can show the guard ran.
- **Negative:**
  - churn: 19 `build_apptainer_exec` call sites (and 7 test calls) gain an argument, the byte-pinned
    command tests are rewritten, and every adapter failure path maps the sentinel;
  - cost: ~2–4 s per launch on the active stack;
  - RunPod solver paths, the DoMINO hand launch and no-SIF runs are refused.
- **Neutral / follow-up (ledgered):** signature verification at launch (an Apptainer ECL bound to the
  platform key) and a hash-while-copy private SIF are complements that would close the residual window;
  an OCI pull-by-digest scheme would revive the RunPod path.

## Links

- ADR-004 (four-fold provenance), ADR-012 (SIF signing), ADR-038 (multi-container roster), ADR-049
  (O-08, H-33), ADR-050 (the hosted case runs under the same guard), ADR-052 (the typed tuple and the
  scheme names).
- CONSTITUTION Invariant 3.
- `aero/adapters/_base.py` (`build_apptainer_exec`), `containers/SHA256SUMS`.
- Stage prompt `docs/handoff-bundle/STAGE-23-foundation-provenance.md`; the operator's decision D3
  (2026-10-21): `docs/handoffs/STAGE-23-foundation-provenance-DONE-2026-10-21.md` §2.
