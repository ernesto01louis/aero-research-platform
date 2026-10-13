# aero-research-platform v0.1.0

The first release. `aero-research-platform` is an open-source, CFD-in-the-loop aerodynamic shape
optimizer. Every reported number carries a four-fold provenance tuple and a combined U95 envelope.
Every claimed improvement must exceed `k·U95` (k = 2), and every optimum is re-verified by CFD
before it is reported. v0.1.0 is the release-first scope of ADR-046:
- portable result crates;
- CI hardening;
- a dependency licence scan;
- JOSS/Zenodo metadata.

## 1. What this release is

- **The airfoil optimizer.** Direct-CFD Bayesian optimization (Stage 15), grid certification
  (Stage 16) and surrogate-accelerated, CFD-verified optimization (Stage 17). The objective is
  NACA-4 camber-line lift-to-drag at Re 5×10⁵, AoA 4°, with k-ω SST.
- **The forward and UQ stack.** OpenFOAM-ESI in Apptainer SIFs, the GCI / ASME V&V 20 numerical
  term, a batch-means statistical term, matched-condition paired deltas, NASA TMR baselines, the
  flapping-wing validation ladder, preCICE FSI coupling, and arbitrary-geometry ingestion.
- **Result crates.** Five committed, self-verifying crates (§3). They follow CONSTITUTION Invariant
  13, RESULTS-MUST-TRAVEL.

## 2. What v0.1.0 does and does not claim

**The optimizer has never been run on a flapping-wing case, and v0.1.0 makes no flapping-wing
optimization claim.**
- The optimizer is demonstrated on the airfoil case only (Stages 15/16/17), gate-honest, and its
  best tier is *validated*.
- The flagship flapping domain ships as a forward capability (Stage 14).
- Rigid-flapping optimization, under a new pre-registration, is Stage 22.
- Flexible-flapping optimization is deferred (ADR-046 S4/S5).

**Stage 14, rigid flapping wing vs. Wang–Birch–Dickinson (2004).**
- The rotation-timing ordering (advanced 0.577 > symmetrical 0.467 > delayed 0.137) is reproduced
  — a pre-registered, non-gated diagnostic.
- The gated symmetrical mean lift misses the experiment by 45.7 % against a pre-registered ±25 %
  band — a documented NO-GO; the band was not relaxed.
- The advanced and delayed mean lifts miss by 38 % and 64 %.
- Overset wake-capture dissipation is the leading hypothesis; it could not be isolated against a
  body-fitted run.
- No four-tuple was recorded for these runs, so the crate is evidence-only and carries no claim.

**Stage 15, CFD-in-the-loop airfoil optimization.** The optimum's matched delta 24.66 did not
exceed its own U95 of 25.37; the gated bar is 2·U95. The family is not grid-converged. The
baseline-to-optimum change is not an improvement claim.

**Stage 16, three-grid certification.** An honest NO-GO by one pre-registered gate: the observed
order is 0.465 against the 0.5 floor. It shipped *validated*.

**Stage 17, surrogate-accelerated optimization.**
- The CFD-verified optimum's delta against the baseline is 24.70 > 2·U95 = 4.15, under a two-grid
  GCI. It is capped at *validated*, because Stage 16 measured sub-first-order convergence.
- The loop's proposals came from smoke-tier, in-loop retrained ensembles, by design, and every
  proposal was CFD-verified.
- The validated surrogate certificate (coverage 0.90, held-out p95 1.31 < 2.5) is a separate fit.
- The optimum exceeds the training corpus's best design by 0.035, inside that quantity's U95 of
  7.03, and that margin is not claimed.
- "Held-out" verification means a deterministic same-grid re-solve.
- The pre-registered speed-up is a degenerate NO-GO.

**Across the record.**
- The airfoil forward model has no experiment anchor.
- The only thesis-grade record is Stage 12's oscillating-cylinder lock-in (Cd 1.993 ± 0.079, with
  the lock-in anchor passed).
- Stage 19's Turek–Hron FSI3 run verified coupling correctness, not application fidelity.
- Stage 20, flexible flapping vs. Heathcote–Gursul, ended NO-GO on infrastructure.
- The mission's own publication bar is not met at v0.1.0: it requires a CFD-verified optimization
  delta on a flapping case that exceeds its U95.

## 3. Result crates

Each crate verifies, and reads back to the same numbers bit for bit, with nothing installed but
the wheel, numpy and pydantic. Cite a result by its **crate digest** (sha256 of its `SHA256SUMS`)
plus its four-tuple.

| crate | claim tier | verdicts | crate digest |
|---|---|---|---|
| `stage12-oscillating-cylinder-lockin` | thesis-grade | thesis-grade-gate GO | `a0ca217d655a243a777574dd3f68b1f6f82542e6e9126bd9e4edfdd43d497773` |
| `stage14-rigid-flapping-wbd2004` | NO CLAIM (evidence only) | forward-validation NO-GO | `438517c449c6d9aa743a2c45d770ccd384b6ab59b817356cf6458a21d27dc989` |
| `stage15-airfoil-optimization` | validated | optimization-claim NO-GO | `bc42503f99e28f3dcbdcd0af4c05e10928f7902db7cb36b3053ce3fa30c8675f` |
| `stage16-airfoil-grid-certification` | validated | grid-certification NO-GO | `0bf8ecae5943929317dd6567efac5e4a94c4555dc9f195e9ef8be3aba70e86b0` |
| `stage17-surrogate-accelerated-optimization` | validated | claim GO, certificate GO, speed-up NO-GO (degenerate) | `b41399231a7e298802aaf9c2a0d8bb1e2b3e36988c321d0f93cc55dccd187383` |

```sh
sha256sum -c SHA256SUMS                                  # inside an extracted crate: coreutils only
python -I -B -m aero.crate verify --expect-digests digests.json <crate>.crate.zip
python -I -B -m aero.crate show <crate>.crate.zip        # what it does and does NOT claim
```

## 4. Install

Install from a clone with [uv](https://docs.astral.sh/uv/): `uv sync`, plus `--extra <name>` per
extra. Alternatively, install the wheel attached to this Release. The PyPI name `aero` belongs to
an unrelated project and is not this platform.

## 5. New in Stage 21

- **`aero/crate/`, format v1 (ADR-047).**
  - RO-Crate 1.3, Process Run Crate 0.6 and PROV-JSON projections.
  - Content-addressed config preimages.
  - The reader hashes before it parses, then parses strictly, and runs under a sandboxed CLI.
  - Required CI `crate round-trip — Invariant 13`, on clean Linux, macOS and Windows runners
    checked against an independent oracle.
- **Dependency licence scan (ADR-048).** A GPL-3.0-compatible allowlist over `uv.lock`, scoped
  (base / supported extras / frozen GPU extras), with reviewed exact-version exceptions. Required
  CI `dependency licence scan — Invariant 5`.
- **Release governance (ADR-049).**
  - The `vX.Y.Z` release-tag gate.
  - `release_readiness.py`, which verifies "all required CI green" instead of assuming it.
  - SHA-pinned actions, pinned runner images, step-scoped secrets, locked installs, gitleaks,
    Dependabot, and a workflow-hygiene test.
- **Correctness hardening.**
  - Finite-only U95 models, with a NaN-safe small-signal guard.
  - IEEE-exact RSS: every committed U95 reproduces bit-identically.
  - Lazy loguru in the core import path.
  - A fail-loud repository-root lookup.
  - A structural `extra="forbid"` test.
- **Docs and community.**
  - The docs now match reality: SECURITY, CONTRIBUTING, the CHANGELOG and the ledger.
  - New CODE_OF_CONDUCT and issue templates.
  - The JOSS paper draft.

## 6. Known issues

- **Two provenance weaknesses**, both stated inside every affected crate:
  - `dvc_input_hash` is a DVC remote-sync-state digest, not a content address;
  - `container_sif_sha256` is a basename lookup in `containers/SHA256SUMS`, not a re-hash at
    launch.
- **The Stage-17 surrogate certificate expires 2027-01-20.** Re-certification needs compute.
- **The four Stage-13 reportable records predate a schema validator.** They are refused, not
  "fixed", and are not crated.
- **`pip-audit` reports known advisories in locked transitive dependencies.** It is informational,
  and a lock refresh is a separate change.
- **The weekly `moving-vv` job times out at its ceiling**, and is known-failing.
- **The tagged tree's README STATUS block reads "(not yet tagged)" by design.** The block is
  regenerated in the first commit after the tag.

## 7. Release artifacts

Attached to this Release, built by `release-readiness.yml` and listed in `SHA256SUMS`:
- the wheel and the sdist, each built twice and compared byte for byte;
- the five `.crate.zip` files;
- the licence report.

## 8. Citation

Zenodo concept DOI: [10.5281/zenodo.20292712](https://doi.org/10.5281/zenodo.20292712). The
version DOI is minted when this Release is published, and is recorded in `docs/release/zenodo.md`.
See `CITATION.cff`.
