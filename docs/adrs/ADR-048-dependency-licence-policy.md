# ADR-048 — Dependency licence policy: a GPL-3.0-compatible allowlist, scoped exceptions, and the licence-scan gate (amends Invariant 5 and Principle 5)

- **Status:** proposed. The Invariant 5 and CLAUDE.md Principle 5 rewording ratifies in the Stage-21
  constitution micro-PR (≥72 h window plus the operator's sign-off). The scanner code lands without
  waiting.
- **Date:** 2026-10-12
- **Deciders:** Operator (Louis Ernesto Schulte Moredo; policy chosen 2026-10-11 as stage decision
  D1); Claude Code agent (Stage 21)
- **Stage:** 21
- **Supersedes:** none. It amends the wording of CONSTITUTION Invariant 5 and CLAUDE.md Principle 5,
  and finally delivers Invariant 5's promised "CI license-scan tooling", which was due at the
  original Stage 16 and never landed.

## Context and problem statement

Invariant 5 reads "GPL-3 / LGPL-3 / Apache-2 / BSD-3 only … No proprietary blob enters this
repository or its container images". Principle 5 repeats the list. Neither the platform nor the
ADR record has ever followed that literally:

- The **base install** already carries MIT (pydantic, typer, loguru), MPL-2.0 (certifi, pathspec,
  tqdm), ISC, PSF-2.0 and ZPL-2.1 packages. It also carries three packages under licences outside
  any GPL-3-compatible reading, all transitive through dvc:
  - grandalf (`GPLv2 | EPLv1`);
  - pygit2 (`GPLv2 with linking exception`, via scmrepo);
  - zc-lockfile (ZPL-2.1, which is GPL-compatible).
- **ADRs already read the list as a posture, not a whitelist:**
  - ADR-008 §D2 accepted MIT JAX-Fluids;
  - ADR-033 §6 accepted MIT typer/loguru and OCCT's LGPL-2.1-with-exception;
  - ADR-035 accepted CalculiX GPL-2-or-later;
  - ADR-010 accepted the NVIDIA CUDA EULA components inside containers.
- **The frozen GPU extras pull proprietary wheels.** `jax-fluids`, `surrogate-smoke` and
  `physicsnemo-cu12` pull 26 NVIDIA wheels declaring `LicenseRef-NVIDIA-Proprietary`, plus
  `cuda-toolkit` with no licence metadata.
- **No licence scan exists.** `.github/workflows/license-audit.yml` is a surrogate-certificate
  watermark plus a dataset cross-licence diff, not a dependency scan, and its watermark step scans
  zero files.
- **Off-the-shelf scanners do not fit.** pip-licenses and liccheck need an installed environment
  (liccheck is also broken by setuptools 82). licensecheck ignores the lockfile. `uv export
  --format cyclonedx1.5` emits no licences, and there is no `uv license`.

## Decision drivers

- A literal implementation of the current text fails on day one, because base deps are MIT.
- The real constraint is GPL-3.0 compatibility of what a user installs with the platform, and no
  proprietary component in the base or supported surface.
- The scan must be exact to `uv.lock`, offline and deterministic in the required check, and must not
  install CUDA wheels.
- FAIL-LOUD: unknown or contradictory metadata fails; every exception is explicit, exact-version
  and reviewed, and goes stale when the lock moves.

## Considered options

1. **Literal four-licence list**, with every other licence as an individual exception. Rejected
   (operator, D1): about 90 exceptions for ordinary permissive licences, which turns review into
   noise.
2. **GPL-3.0-compatible allowlist, scoped by extra, with reviewed exceptions.** **Chosen** (operator,
   D1).
3. **As option 2, and move dvc from the base dependencies to the `provenance` extra.** Not chosen
   (operator, D1). dvc stays in the base dependencies, and its two GPL-2-family transitive packages
   are carried as reviewed exceptions.

## Decision outcome

### Allowlist (SPDX)

`MIT`, `MIT-0`, `MIT-CMU`, `X11`, `HPND`, `BSD-1-Clause`, `BSD-2-Clause`, `BSD-3-Clause`, `0BSD`,
`Apache-2.0`, `Apache-2.0 WITH LLVM-exception`, `ISC`, `PSF-2.0`, `Python-2.0`, `MPL-2.0`,
`LGPL-2.1-only`, `LGPL-2.1-or-later`, `LGPL-3.0-only`, `LGPL-3.0-or-later`, `GPL-2.0-or-later`,
`GPL-3.0-only`, `GPL-3.0-or-later`, `ZPL-2.1`, `Zlib`, `CC0-1.0`, `Unlicense`, `BSL-1.0`,
`CNRI-Python`.

These are GPL-3.0-compatible per the FSF licence list. An SPDX expression passes when an `AND`
requires every term to be allowed and an `OR` requires one; `WITH` pairs must be listed explicitly.

### Normalisation ladder (per package, per exact locked version)

1. `License-Expression` (PEP 639);
2. a single-line SPDX-like `License` field, with deprecated ids mapped (`LGPL-3.0` →
   `LGPL-3.0-only`, `GPL-3.0` → `GPL-3.0-only`);
3. a single specific `License ::` classifier.

The bare classifier `License :: OSI Approved :: BSD License` normalises to `LicenseRef-OSI-BSD-family`.
That id is allowlisted, because every OSI-approved BSD variant is GPL-3.0-compatible, and the report
lists those packages separately.

Anything else fails as UNKNOWN: ambiguous values, multi-line licence text, missing metadata, or a
`License` field that contradicts its classifier (e.g. `nvidia-nvtx`). Such a package needs a
reviewed exception.

### Scopes

Every locked extra belongs to exactly one scope:

| Scope | Extras | NVIDIA proprietary allowed? |
|---|---|---|
| `base` | the base dependencies | no |
| `supported-extras` | cad, dev, gpu-rental, nekrs, openfoam, precice, provenance, pyfr, su2, vv | no |
| `gpu-frozen` | jax-fluids, surrogate-smoke, physicsnemo-cu12 (frozen-optional per ADR-013) | **yes**: `LicenseRef-NVIDIA-*` and the reviewed CUDA-runtime exceptions, on ADR-010's footing |

A package reachable from several scopes must satisfy every one of them. The **base and
supported-extras scopes are proprietary-free**.

### Exceptions

`ci/licence/exceptions.toml` holds the exceptions. Each entry is keyed by exact `name==version`, plus
the commit for a git source, and carries:
- the reviewed SPDX expression;
- the scopes it applies in;
- the reason;
- this ADR or a later one;
- an https evidence URL;
- the reviewer;
- the date.

An exception that is stale (the version moved), unused, or used outside its scopes **fails** the
scan.

Initial base-scope exceptions (D1):
- **grandalf** (`GPLv2 | EPLv1`) and **pygit2** (GPL-2.0 with a linking exception). Reason: transitive
  runtime dependencies of dvc (grandalf for dvc's DAG rendering; pygit2 via scmrepo). The `aero`
  package never imports either, and neither is redistributed with the platform; they are resolved
  and installed by the user's installer. Both are re-reviewed whenever dvc moves.
- **git source `jaxfluids@ac7c090f`**: MIT per its LICENSE at that commit (ADR-008 §D2).

### Scanner

`scripts/licence_scan.py` uses only the stdlib and runs as `python3 -I`:
- It parses `uv.lock` with `tomllib` and computes each scope's closure.
- It reads licence metadata from a committed snapshot, `ci/licence/metadata-snapshot.json`, bound
  per package to the lock's name, version, source and artifact sha256. The snapshot is refreshed
  from PEP 658 `.metadata` files, which are verified against the PEP 691 core-metadata hashes.
  Sdist-only packages are read from `PKG-INFO` in memory, after the sdist sha256 is checked against
  the lock. Nothing is ever built or installed.
- The required check is offline and deterministic. A non-required job re-fetches and re-verifies
  the metadata online.
- It writes a sorted JSON report with no timestamps.

### Enforcement

The required context **`dependency licence scan — Invariant 5`**, starting with `uv lock --check`.
Path logic stays inside the job; there is never a workflow-level path filter. In addition, any new
heavy dependency needs an ADR naming its licence, as today.

### Draft Invariant 5 (text final at the micro-PR)

> **Invariant 5 — LICENSE-POSTURE — GPL-3.0-compatible.** The platform is GPL-3.0-or-later. Every
> package `uv.lock` can install carries a licence on the ADR-048 allowlist (GPL-3.0-compatible:
> MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, LGPL, GPL-2.0-or-later, GPL-3.0, ZPL-2.1, Zlib, CC0,
> Unlicense, BSL-1.0, …), or a reviewed exact-version exception. The base install and the supported
> extras are proprietary-free. NVIDIA proprietary CUDA components are admitted only in the
> frozen-optional GPU extras (`jax-fluids`, `surrogate-smoke`, `physicsnemo-cu12`) and their
> container images (ADR-010). No commercial CFD or CAE dependency, no closed-source MKL build.
> **Enforcement:** required check `dependency licence scan — Invariant 5`; an ADR for every new
> heavy dependency naming its licence.

CLAUDE.md Principle 5 is reworded to match in the same micro-PR.

### Consequences

- **Positive:**
  - The licence posture becomes machine-checked and lock-exact for the first time.
  - The NVIDIA exposure is visible and scoped instead of implicit.
- **Negative:**
  - The base install still contains two GPL-2-family packages via dvc, carried as exceptions. If
    the operator later moves dvc into the `provenance` extra, those exceptions disappear.
  - The first snapshot needs a one-time evidence review of about 40 non-GPU entries.
- **Out of scope:** container-image licence scanning and SBOMs. They are outside the Python lock,
  and SECURITY.md defers the SBOM to after v0.1.

## Links

- CONSTITUTION Invariant 5; CLAUDE.md Principle 5; ADR-001, ADR-008 §D2, ADR-010, ADR-013, ADR-033
  §6, ADR-035; ADR-049.
- PEP 639, PEP 658, PEP 691; FSF licence list (https://www.gnu.org/licenses/license-list.html).
