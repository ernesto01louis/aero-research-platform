#!/usr/bin/env python3
"""Stage 20 — acquire the pinned `perpendicular-flap` tutorial for the CalculiX smoke.

Stage 19 vendored `turek-hron-fsi3/` + `tools/` from `precice/tutorials` at commit
`cd33e2db…`. Stage 20 needs a SECOND subtree from the SAME commit — the CalculiX
perpendicular-flap case — so the two-container smoke runs bytes upstream authored
rather than a coupling we invented.

**A separate archive, not an extended one.** The Stage-19 archive's sha256 is
`TutorialPin.archive_sha256` in the FSI3 case spec and its manifest is the integrity
contract behind a closed, tagged verdict. Adding files to it would change that digest
and retroactively invalidate the Stage-19 record. Two archives, two manifests.

Determinism matters, because the archive digest is a pin: the re-tar sorts paths, zeroes
mtimes, sets numeric 0/0 ownership and gzips with `-n` (no filename/timestamp header), so
re-running this script on any machine reproduces the same bytes. GitHub codeload tarballs
themselves are NOT byte-stable over time, which is exactly why the per-file manifest —
not the archive checksum — is what `materialize_tutorial` verifies against.

Usage (from the repo root, on a host with outbound network):

    python scripts/stage20_acquire_perpendicular_flap.py
    python scripts/stage20_acquire_perpendicular_flap.py --archive /path/to/codeload.tar.gz

Then, as the script prints:

    dvc add data/references/fsi/precice_perpendicular_flap/precice-tutorials-perpendicular-flap.tar.gz
    dvc push -r aero-minio
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: The SAME pin Stage 19 vetted (ADR-035 §Version pins). Using a different commit for the
#: smoke would mean the conventions it teaches us are not the conventions the gated case
#: inherits.
TUTORIALS_COMMIT = "cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e"
TUTORIALS_BRANCH = "develop"
CODELOAD = f"https://codeload.github.com/precice/tutorials/tar.gz/{TUTORIALS_COMMIT}"

_DEST_DIR = _REPO_ROOT / "data" / "references" / "fsi" / "precice_perpendicular_flap"
_ARCHIVE_NAME = "precice-tutorials-perpendicular-flap.tar.gz"
_MANIFEST_NAME = "tutorials_pin_manifest.csv"

#: Subtrees taken verbatim. `tools/` is required because upstream's `run.sh` scripts
#: source `../../tools/log.sh`, i.e. OUTSIDE the case directory (Stage-19 gotcha 11).
_SUBTREES = ("perpendicular-flap/", "tools/")
#: Documentation images are large and play no part in a solve.
_EXCLUDE_PARTS = ("images/",)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(dest: Path) -> Path:
    """Download the codeload tarball for the pinned commit."""
    print(f"fetching {CODELOAD}")
    with urllib.request.urlopen(CODELOAD, timeout=120) as response:
        payload = response.read()
    dest.write_bytes(payload)
    print(f"  {len(payload)} B, sha256 {_sha256_bytes(payload)}")
    return dest


def _wanted(member_name: str) -> str | None:
    """Map a codeload member path to its repo-relative path, or None to skip it.

    Codeload prefixes everything with `tutorials-<commit>/`; that prefix is stripped so
    the archive matches the layout `materialize_tutorial` expects.
    """
    parts = member_name.split("/", 1)
    if len(parts) != 2 or not parts[1]:
        return None
    relative = parts[1]
    if not relative.startswith(_SUBTREES):
        return None
    if any(excluded in relative for excluded in _EXCLUDE_PARTS):
        return None
    return relative


def _collect(codeload: Path) -> dict[str, bytes]:
    """Read every wanted regular file out of the codeload tarball."""
    files: dict[str, bytes] = {}
    with tarfile.open(codeload, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            relative = _wanted(member.name)
            if relative is None:
                continue
            handle = tar.extractfile(member)
            if handle is None:  # pragma: no cover - isfile() implies a payload
                raise RuntimeError(f"could not read {member.name} from the codeload archive")
            files[relative] = handle.read()
    if not files:
        raise RuntimeError(
            f"no files matched {_SUBTREES} in {codeload} — the pin or the upstream layout moved"
        )
    return files


def _write_deterministic_archive(files: dict[str, bytes], dest: Path) -> str:
    """Re-tar reproducibly and return the archive's sha256.

    Sorted paths, zeroed mtime, numeric 0/0 ownership, mode normalised to 0644/0755, and
    `gzip` with mtime=0 so the gzip header carries no timestamp. Without all five, two
    runs of this script produce different bytes and the pin means nothing.
    """
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name in sorted(files):
            payload = files[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if name.endswith(".sh") or name.endswith(".py") else 0o644
            tar.addfile(info, io.BytesIO(payload))
    import gzip

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    digest = _sha256_bytes(dest.read_bytes())
    print(f"wrote {dest.relative_to(_REPO_ROOT)} ({dest.stat().st_size} B)")
    print(f"  archive sha256 {digest}")
    return digest


def _write_manifest(files: dict[str, bytes], dest: Path) -> None:
    """Per-file sha256 — the integrity contract `materialize_tutorial` verifies against."""
    lines = [
        f"# Per-file sha256 of precice/tutorials @ {TUTORIALS_COMMIT} (branch {TUTORIALS_BRANCH}),",
        "# subtrees perpendicular-flap/ (minus images/) and tools/. This manifest is the",
        "# integrity contract: GitHub codeload tarballs are not guaranteed byte-stable,",
        "# so aero.adapters.precice.materialize_tutorial verifies EVERY file against",
        "# it after extraction. Missing, altered and unexpected files are all fatal.",
        "sha256,path",
    ]
    lines.extend(f"{_sha256_bytes(files[name])},{name}" for name in sorted(files))
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(_REPO_ROOT)} ({len(files)} files)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="a pre-downloaded codeload tarball (skips the network fetch)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=_DEST_DIR,
        help="output directory (default: data/references/fsi/precice_perpendicular_flap)",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="stage20-acquire-") as tmp:
        codeload = args.archive or _fetch(Path(tmp) / "codeload.tar.gz")
        files = _collect(codeload)

        # Sanity: the smoke is meaningless without the CalculiX participant and the
        # coupling configuration, so refuse a subtree that does not contain them rather
        # than shipping an archive that fails much later, inside a container.
        required = (
            "perpendicular-flap/precice-config.xml",
            "perpendicular-flap/solid-calculix/config.yml",
            "perpendicular-flap/fluid-openfoam/system/blockMeshDict",
        )
        missing = [name for name in required if name not in files]
        if missing:
            print(f"ERROR: the pinned tutorial is missing {missing}", file=sys.stderr)
            print(
                f"       (got {len(files)} files; upstream layout may have moved)", file=sys.stderr
            )
            return 1

        args.dest.mkdir(parents=True, exist_ok=True)
        archive = args.dest / _ARCHIVE_NAME
        digest = _write_deterministic_archive(files, archive)
        (args.dest / f"{_ARCHIVE_NAME}.sha256").write_text(digest + "\n", encoding="utf-8")
        _write_manifest(files, args.dest / _MANIFEST_NAME)

        gitignore = args.dest / ".gitignore"
        gitignore.write_text(f"/{_ARCHIVE_NAME}\n", encoding="utf-8")

    print()
    print("TutorialPin for the smoke:")
    print(f'    commit="{TUTORIALS_COMMIT}"')
    print(f'    archive_sha256="{digest}"')
    print()
    print("next:")
    rel = archive.relative_to(_REPO_ROOT)
    print(f"    dvc add {rel}")
    print("    dvc push -r aero-minio")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
