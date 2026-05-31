# Dataset licences in this repository

| Dataset | Licence | Upstream | Sample type yielded | Cert tag |
|---|---|---|---|---|
| AhmedML | CC-BY-SA-4.0 | https://huggingface.co/datasets/neashton/ahmedml | `Sample(kind="commercial")` | `non_commercial=False` |
| WindsorML | CC-BY-SA-4.0 | https://huggingface.co/datasets/neashton/windsorml | `Sample(kind="commercial")` | `non_commercial=False` |
| DrivAerML | CC-BY-SA-4.0 | https://huggingface.co/datasets/neashton/drivaerml | `Sample(kind="commercial")` | `non_commercial=False` |
| **DrivAerNet++** | **CC-BY-NC-4.0** | https://dataverse.harvard.edu/dataverse/DrivAerNet | `TaintedSample(kind="non_commercial")` | **`non_commercial=True`** |

## Quarantine boundary

DrivAerNet++ is the **only CC-BY-NC** dataset in the bundle. Its loader
lives in a structurally separate subpackage:

  `aero/surrogates/_common/loaders/non_commercial/`

Any module importing from that subpackage must satisfy one of:

1. Produce a `CertificateOfValidity(non_commercial=True)` somewhere in the
   same file (the natural shape — training scripts).
2. Carry the `# non-commercial: justified` pragma on the import line
   (audited exception — tests, license-aware tooling).

The `.github/workflows/non-commercial-fence.yml` CI workflow enforces this
on every PR.

## What inheriting a licence means

* A model trained on CC-BY-SA-4.0 data → carries CC-BY-SA-4.0 obligations
  (give attribution, distribute derivatives under the same licence)
* A model trained on CC-BY-NC-4.0 data → carries CC-BY-NC-4.0 obligations
  (no commercial use, ever)
* A model trained on **both** → inherits the **more restrictive** licence
  (CC-BY-NC-4.0 wins)
* Predictions from such a model are derivative works; the obligation
  propagates to anything that embeds them downstream

## The structural defences

| Layer | Mechanism | File |
|---|---|---|
| **Loader fence** | constructor `LicenseAcknowledgmentRequired` | `aero/surrogates/_common/loaders/non_commercial/drivaernet_plus_plus.py` |
| **Sample taint** | `TaintedSample` discriminated union | `aero/surrogates/_common/base.py` |
| **Surrogate taint** | `_non_commercial` flag auto-flips on ingest | `aero/surrogates/_common/base.py` |
| **Cert write-once-True** | `model_copy` override refuses `True → False` | `aero/surrogates/_common/certificate.py` |
| **Watermark** | forced `_nc` surrogate-name suffix | `aero/surrogates/_common/certificate.py` |
| **Citation trail** | `attribution_required` cert field | `aero/surrogates/_common/certificate.py` |
| **MLflow trail** | `license_id` + `attribution_required` tags | `aero/surrogates/_common/certificate.py` |
| **Fence CI** | greps imports of `non_commercial/` subpackage | `.github/workflows/non-commercial-fence.yml` |
| **License-audit CI** | scans new artifacts for cross-license contamination | `.github/workflows/license-audit.yml` |
| **ADR-009** | documents the full posture | `docs/adrs/ADR-009-cc-by-nc-quarantine-posture.md` |

## What you, the operator, must still do manually

The structural defences cover accidental contamination. **They do NOT
stop intentional misuse.** You must additionally:

* Cite the dataset authors in every publication, talk, README, blog post,
  or public demo
* Never publish CC-BY-NC-trained weights to a public registry without the
  license label visible
* Never use CC-BY-NC-trained models for paid work (consulting, product
  engineering, monetised hosting)
* When in doubt about a specific use case, email the dataset authors for
  a written waiver

See `docs/adrs/ADR-009-cc-by-nc-quarantine-posture.md` for the full
legal-posture analysis.
