"""scripts/licence_scan.py: the dependency licence scan (CONSTITUTION Invariant 5; ADR-048)."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "licence_scan", REPO / "scripts" / "licence_scan.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["licence_scan"] = module
    spec.loader.exec_module(module)
    return module


ls = _load()

H = {n: hashlib.sha256(n.encode()).hexdigest() for n in "abcdefghijklmn"}

# A 12-package lock: the root "proj" with base deps a, b; extras dev (c, and a[fast]) and gpu (d).
LOCK = f"""
version = 1
revision = 3
requires-python = ">=3.12"

[[package]]
name = "proj"
version = "0.0.1"
source = {{ editable = "." }}
dependencies = [{{ name = "a" }}, {{ name = "b", marker = "sys_platform == 'win32'" }}]

[package.optional-dependencies]
dev = [{{ name = "a", extra = ["fast"] }}, {{ name = "c" }}]
gpu = [{{ name = "d" }}]

[[package]]
name = "a"
version = "1.0"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [{{ name = "e" }}]
wheels = [{{ url = "https://files.example/a-1.0-py3-none-any.whl", hash = "sha256:{H["a"]}" }}]

[package.optional-dependencies]
fast = [{{ name = "f" }}]

[[package]]
name = "b"
version = "2.0"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files.example/b-2.0.tar.gz", hash = "sha256:{H["b"]}" }}

[[package]]
name = "c"
version = "3.0"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [{{ name = "g" }}, {{ name = "h" }}]
wheels = [{{ url = "https://files.example/c-3.0-py3-none-any.whl", hash = "sha256:{H["c"]}" }}]

[[package]]
name = "d"
version = "4.0"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [{{ name = "nv" }}, {{ name = "i" }}, {{ name = "gitpkg" }}]
wheels = [{{ url = "https://files.example/d-4.0-py3-none-any.whl", hash = "sha256:{H["d"]}" }}]

[[package]]
name = "e"
version = "1.1"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files.example/e-1.1-py3-none-any.whl", hash = "sha256:{H["e"]}" }}]

[[package]]
name = "f"
version = "1.2"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files.example/f-1.2-py3-none-any.whl", hash = "sha256:{H["f"]}" }}]

[[package]]
name = "g"
version = "1.3"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files.example/g-1.3-py3-none-any.whl", hash = "sha256:{H["g"]}" }}]

[[package]]
name = "h"
version = "1.4"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files.example/h-1.4-py3-none-any.whl", hash = "sha256:{H["h"]}" }}]

[[package]]
name = "i"
version = "1.5"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files.example/i-1.5-py3-none-any.whl", hash = "sha256:{H["i"]}" }}]

[[package]]
name = "nv"
version = "12.0"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files.example/nv-12.0-py3-none-manylinux.whl", hash = "sha256:{H["n"]}" }}]

[[package]]
name = "gitpkg"
version = "0.1"
source = {{ git = "https://example.org/gitpkg.git?rev=abc#abcdef0123" }}
"""

POLICY = {
    "allow": [
        "MIT",
        "Apache-2.0",
        "BSD-3-Clause",
        "LicenseRef-OSI-BSD-family",
        "LGPL-3.0-or-later",
    ],
    "allow_with": ["Apache-2.0 WITH LLVM-exception"],
    "scopes": {
        "base": {"base": True},
        "supported-extras": {"extras": ["dev"]},
        "gpu-frozen": {"extras": ["gpu"], "allow_patterns": ["LicenseRef-NVIDIA-*"]},
    },
}


def _entry(name: str, version: str, sha: str, **meta: Any) -> dict[str, Any]:
    base = {
        "version": version,
        "source": "registry",
        "artifact": f"{name}.whl",
        "artifact_sha256": sha,
        "metadata_sha256": "0" * 64,
        "metadata_version": "2.4",
        "license_expression": None,
        "license": None,
        "license_multiline": False,
        "license_text_sha256": None,
        "classifiers": [],
    }
    return {**base, **meta}


SNAPSHOT = {
    "format": 1,
    "index": "https://pypi.org/simple",
    "packages": {
        "a": _entry("a", "1.0", H["a"], license_expression="MIT"),
        "b": _entry("b", "2.0", H["b"], license="Apache 2.0"),
        "c": _entry("c", "3.0", H["c"], classifiers=["License :: OSI Approved :: BSD License"]),
        "d": _entry("d", "4.0", H["d"], license_expression="Apache-2.0 OR MIT"),
        "e": _entry("e", "1.1", H["e"], license_expression="BSD-3-Clause"),
        "f": _entry("f", "1.2", H["f"], license_expression="Apache-2.0 WITH LLVM-exception"),
        "g": _entry(
            "g",
            "1.3",
            H["g"],
            license="MIT",
            classifiers=["License :: OSI Approved :: MIT License"],
        ),
        "h": _entry(
            "h",
            "1.4",
            H["h"],
            license_multiline=True,
            classifiers=["License :: OSI Approved :: MIT License"],
        ),
        "i": _entry("i", "1.5", H["i"], license_expression="MIT AND LGPL-3.0-or-later"),
        "nv": _entry(
            "nv",
            "12.0",
            H["n"],
            license="LicenseRef-NVIDIA-Proprietary",
            classifiers=["License :: Other/Proprietary License"],
        ),
        "gitpkg": {
            "version": "0.1",
            "source": "git+https://example.org/gitpkg.git?rev=abc#abcdef0123",
            "artifact": None,
            "artifact_sha256": None,
            "metadata_sha256": None,
        },
    },
}

GIT_EXCEPTION = {
    "package": "gitpkg",
    "version": "0.1",
    "commit": "abcdef0123",
    "kind": "identify",
    "reviewed_spdx": "MIT",
    "scopes": ["gpu-frozen"],
    "reason": "git source",
    "adr": "ADR-048",
    "evidence": "https://example.org/gitpkg/LICENSE",
    "reviewer": "test",
    "date": "2026-10-12",
}


@pytest.fixture
def lock(tmp_path: Path) -> Path:
    p = tmp_path / "uv.lock"
    p.write_text(LOCK)
    return p


def _check(
    lock: Path,
    snapshot: dict[str, Any] | None = None,
    exceptions: list[dict[str, Any]] | None = None,
) -> tuple[list[Any], list[str]]:
    verdicts, problems, _ = ls.check(
        lock, snapshot or SNAPSHOT, POLICY, [GIT_EXCEPTION] if exceptions is None else exceptions
    )
    return verdicts, problems


def _failures(verdicts: list[Any]) -> dict[str, list[str]]:
    return {v.name: v.problems for v in verdicts if v.status == "FAIL"}


# --- SPDX ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "canonical"),
    [
        ("MIT", "MIT"),
        ("MIT OR Apache-2.0 AND BSD-3-Clause", "MIT OR Apache-2.0 AND BSD-3-Clause"),
        ("(MIT OR Apache-2.0) AND BSD-3-Clause", "(MIT OR Apache-2.0) AND BSD-3-Clause"),
        ("GPL-2.0+", "GPL-2.0-or-later"),
        ("LGPL-3.0", "LGPL-3.0-only"),
        ("Apache-2.0 WITH LLVM-exception", "Apache-2.0 WITH LLVM-exception"),
        ("mit or apache-2.0", "mit OR apache-2.0"),
    ],
)
def test_spdx_parse_and_render(expr: str, canonical: str) -> None:
    assert ls.render(ls.parse_spdx(expr)) == canonical


@pytest.mark.parametrize("bad", ["", "MIT OR", "(MIT", "MIT)", "AND MIT", "MIT WITH", "GPL v2"])
def test_spdx_refuses_malformed(bad: str) -> None:
    with pytest.raises(ls.SpdxError):
        ls.parse_spdx(bad)


def test_and_needs_every_term_or_needs_one_with_needs_the_pair() -> None:
    ok = {"MIT", "Apache-2.0 WITH LLVM-exception"}.__contains__
    assert ls.allowed(ls.parse_spdx("MIT OR GPL-2.0-only"), ok)
    assert not ls.allowed(ls.parse_spdx("MIT AND GPL-2.0-only"), ok)
    assert ls.allowed(ls.parse_spdx("Apache-2.0 WITH LLVM-exception"), ok)
    assert not ls.allowed(ls.parse_spdx("MIT WITH LLVM-exception"), ok)


# --- the normalisation ladder ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("meta", "spdx"),
    [
        ({"license_expression": "MIT", "license": "garbage"}, "MIT"),  # step 1 wins
        ({"license": "Apache 2.0"}, "Apache-2.0"),  # step 2, mapped text
        ({"license": "BSD-3-Clause OR MIT"}, "BSD-3-Clause OR MIT"),  # step 2, known SPDX ids
        ({"classifiers": ["License :: OSI Approved :: BSD License"]}, "LicenseRef-OSI-BSD-family"),
        (
            {"license": "BSD-3-Clause", "classifiers": ["License :: OSI Approved :: BSD License"]},
            "BSD-3-Clause",
        ),
        (
            {"license_multiline": True, "classifiers": ["License :: OSI Approved :: MIT License"]},
            "MIT",
        ),
        (
            {
                "license": "LicenseRef-NVIDIA-Proprietary",
                "classifiers": ["License :: Other/Proprietary License"],
            },
            "LicenseRef-NVIDIA-Proprietary",
        ),
        (
            {
                "license": "UNKNOWN",
                "classifiers": [
                    "License :: OSI Approved",
                    "License :: OSI Approved :: MIT License",
                ],
            },
            "MIT",
        ),
    ],
)
def test_the_ladder_identifies(meta: dict[str, Any], spdx: str) -> None:
    assert ls.normalise(meta).spdx == spdx


@pytest.mark.parametrize(
    "meta",
    [
        {},  # no metadata at all
        {"license": "GPL"},  # not an SPDX id
        {"license": "LGPL with exceptions"},  # looks like an expression, names no real id
        {"license": "Dual License", "classifiers": ["License :: OSI Approved :: MIT License"]},
        {
            "license": "Apache 2.0",
            "classifiers": ["License :: Other/Proprietary License"],
        },  # contradiction
        {
            "classifiers": [
                "License :: OSI Approved :: MIT License",
                "License :: OSI Approved :: Apache Software License",
            ]
        },
        {"license_multiline": True},
        {
            "classifiers": [
                "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)"
            ]
        },
        {"license_expression": "MIT OR"},
    ],
)
def test_the_ladder_refuses_to_guess(meta: dict[str, Any]) -> None:
    assert ls.normalise(meta).spdx is None


# --- closures and scopes --------------------------------------------------------------------------


def test_closures_follow_extras_and_ignore_markers(lock: Path) -> None:
    root, packages, _ = ls.load_lock(lock)
    scopes = ls.scope_closures(root, packages, POLICY)
    assert scopes["base"] == {"a", "b", "e"}  # b is win32-only: markers are ignored (universal)
    assert scopes["supported-extras"] == {"a", "e", "f", "c", "g", "h"}  # a[fast] -> f
    assert scopes["gpu-frozen"] == {"d", "nv", "i", "gitpkg"}


def test_every_locked_extra_belongs_to_exactly_one_scope(lock: Path) -> None:
    root, packages, _ = ls.load_lock(lock)
    unscoped = copy.deepcopy(POLICY)
    unscoped["scopes"]["gpu-frozen"]["extras"] = []
    with pytest.raises(SystemExit, match="unscoped"):
        ls.scope_closures(root, packages, unscoped)
    twice = copy.deepcopy(POLICY)
    twice["scopes"]["supported-extras"]["extras"] = ["dev", "gpu"]
    with pytest.raises(SystemExit, match="in scopes"):
        ls.scope_closures(root, packages, twice)


# --- the check ------------------------------------------------------------------------------------


def test_the_synthetic_lock_passes(lock: Path) -> None:
    verdicts, problems = _check(lock)
    assert problems == [] and _failures(verdicts) == {}
    by = {v.name: v for v in verdicts}
    assert by["gitpkg"].status == "identified-by-exception"
    assert by["a"].scopes == ["base", "supported-extras"]


def test_proprietary_is_admitted_only_in_gpu_frozen(lock: Path) -> None:
    snap = copy.deepcopy(SNAPSHOT)
    snap["packages"]["e"] = _entry("e", "1.1", H["e"], license="LicenseRef-NVIDIA-Proprietary")
    verdicts, _ = _check(lock, snap)
    fails = _failures(verdicts)
    assert set(fails) == {"e"}
    assert any("'base'" in p for p in fails["e"]) and any(
        "'supported-extras'" in p for p in fails["e"]
    )


def test_an_unknown_licence_fails_and_names_the_reason(lock: Path) -> None:
    snap = copy.deepcopy(SNAPSHOT)
    snap["packages"]["g"] = _entry("g", "1.3", H["g"], license="GPL")
    fails = _failures(_check(lock, snap)[0])
    assert list(fails) == ["g"] and "UNKNOWN" in fails["g"][0]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version": "1.0.1"}, "snapshot is for 1.0.1"),
        ({"artifact_sha256": "f" * 64}, "artifact sha256"),
    ],
)
def test_the_snapshot_is_bound_to_the_lock(
    lock: Path, change: dict[str, Any], message: str
) -> None:
    snap = copy.deepcopy(SNAPSHOT)
    snap["packages"]["a"].update(change)
    fails = _failures(_check(lock, snap)[0])
    assert any(message in p for p in fails["a"])


def test_snapshot_entries_for_packages_not_in_the_lock_fail(lock: Path) -> None:
    snap = copy.deepcopy(SNAPSHOT)
    snap["packages"]["zombie"] = _entry("zombie", "9", "0" * 64, license_expression="MIT")
    _, problems = _check(lock, snap)
    assert any("not in the lock" in p for p in problems)


def test_a_missing_snapshot_entry_fails(lock: Path) -> None:
    snap = copy.deepcopy(SNAPSHOT)
    del snap["packages"]["h"]
    assert "h" in _failures(_check(lock, snap)[0])


def test_exceptions_identify_admit_and_go_stale(lock: Path) -> None:
    snap = copy.deepcopy(SNAPSHOT)
    snap["packages"]["c"] = _entry("c", "3.0", H["c"], license="GPLv2 | EPLv1")
    admit = {
        **GIT_EXCEPTION,
        "package": "c",
        "version": "3.0",
        "commit": None,
        "kind": "admit",
        "reviewed_spdx": "GPL-2.0-only OR EPL-1.0",
        "scopes": ["supported-extras"],
    }
    verdicts, problems = _check(lock, snap, [GIT_EXCEPTION, admit])
    assert problems == [] and _failures(verdicts) == {}
    assert {v.name: v.status for v in verdicts}["c"] == "admitted-by-exception"

    # Stale: the lock moved past the reviewed version -> the exception is unused AND c fails.
    stale = {**admit, "version": "2.9"}
    verdicts, problems = _check(lock, snap, [GIT_EXCEPTION, stale])
    assert "c" in _failures(verdicts) and any("unused exception c==2.9" in p for p in problems)

    # Out of scope: c is reachable from supported-extras, the exception names only gpu-frozen.
    narrow = {**admit, "scopes": ["gpu-frozen"]}
    assert any(
        "does not cover" in p
        for p in _failures(_check(lock, snap, [GIT_EXCEPTION, narrow])[0])["c"]
    )


def test_unneeded_exceptions_fail(lock: Path) -> None:
    identify = {
        **GIT_EXCEPTION,
        "package": "a",
        "version": "1.0",
        "commit": None,
        "scopes": ["base", "supported-extras"],
    }
    fails = _failures(_check(lock, None, [GIT_EXCEPTION, identify])[0])
    assert any("unneeded 'identify'" in p for p in fails["a"])
    admit = {**identify, "kind": "admit"}
    fails = _failures(_check(lock, None, [GIT_EXCEPTION, admit])[0])
    assert any("unneeded 'admit'" in p for p in fails["a"])


def test_an_identify_exception_must_still_pass_the_allowlist(lock: Path) -> None:
    wrong = {**GIT_EXCEPTION, "reviewed_spdx": "GPL-2.0-only"}
    fails = _failures(_check(lock, None, [wrong])[0])
    assert any("not allowed in scope 'gpu-frozen'" in p for p in fails["gitpkg"])


def test_a_git_exception_is_pinned_to_its_commit(lock: Path) -> None:
    moved = {**GIT_EXCEPTION, "commit": "fedcba9876"}
    fails = _failures(_check(lock, None, [moved])[0])
    assert any("exception is for commit" in p for p in fails["gitpkg"])


def test_exceptions_need_their_review_fields(lock: Path) -> None:
    bare = {**GIT_EXCEPTION, "evidence": "http://example.org", "reviewer": ""}
    _, problems = _check(lock, None, [bare])
    assert any("https" in p for p in problems) and any("'reviewer'" in p for p in problems)


# --- refresh (online), against a fake index -------------------------------------------------------


def _metadata(lic: str) -> bytes:
    return f"Metadata-Version: 2.4\nName: x\nVersion: 1\nLicense-Expression: {lic}\nClassifier: Programming Language :: Python\n\n".encode()


def _sdist(name: str, pkg_info: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(f"{name}-2.0/PKG-INFO")
        info.size = len(pkg_info)
        tf.addfile(info, io.BytesIO(pkg_info))
    return buf.getvalue()


class FakeIndex:
    def __init__(self, lock: Path) -> None:
        _, self.packages, _ = ls.load_lock(lock)
        self.meta = {n: _metadata("MIT") for n in self.packages}
        self.sdist_bytes = _sdist(
            "b", b"Metadata-Version: 2.1\nName: b\nVersion: 2.0\nLicense: Apache 2.0\n\n"
        )
        self.tamper: set[str] = set()

    def __call__(self, url: str, accept: str | None) -> bytes:
        if url.startswith(ls.INDEX):
            name = url.removeprefix(ls.INDEX + "/").strip("/")
            files = []
            for wurl, sha in self.packages[name].wheels:
                files.append(
                    {
                        "filename": wurl.rsplit("/", 1)[-1],
                        "url": wurl,
                        "hashes": {"sha256": sha},
                        "core-metadata": {"sha256": hashlib.sha256(self.meta[name]).hexdigest()},
                    }
                )
            return json.dumps({"files": files}).encode()
        if url.endswith(".metadata"):
            name = url.rsplit("/", 1)[-1].split("-", 1)[0]
            return self.meta[name] + (b"x" if name in self.tamper else b"")
        if url.endswith(".tar.gz"):
            return self.sdist_bytes
        raise AssertionError(url)


def test_refresh_reads_hash_verified_metadata(lock: Path) -> None:
    index = FakeIndex(lock)
    lock.write_text(LOCK.replace(H["b"], hashlib.sha256(index.sdist_bytes).hexdigest()))
    snap = ls.refresh(lock, fetch=index, workers=2)
    assert snap["packages"]["a"]["license_expression"] == "MIT"
    assert snap["packages"]["b"]["license"] == "Apache 2.0"  # from the sdist's PKG-INFO
    assert snap["packages"]["gitpkg"]["artifact"] is None
    assert "proj" not in snap["packages"]
    assert ls.refresh(lock, fetch=index, workers=4) == snap  # deterministic


def test_refresh_refuses_tampered_metadata_and_a_wrong_sdist(lock: Path) -> None:
    index = FakeIndex(lock)
    index.tamper.add("a")
    with pytest.raises(SystemExit, match="PEP 691 hash"):
        ls.refresh(lock, fetch=index, workers=1)
    index.tamper.clear()
    with pytest.raises(SystemExit, match="sdist does not match"):
        ls.refresh(lock, fetch=index, workers=1)  # b's sdist hash in LOCK is a placeholder


# --- the committed policy, exceptions and snapshot ------------------------------------------------


def test_the_repository_passes_its_own_scan() -> None:
    snapshot = json.loads((REPO / "ci/licence/metadata-snapshot.json").read_text(encoding="utf-8"))
    policy = tomllib.loads((REPO / "ci/licence/policy.toml").read_text(encoding="utf-8"))
    exceptions = tomllib.loads((REPO / "ci/licence/exceptions.toml").read_text(encoding="utf-8"))[
        "exception"
    ]
    verdicts, problems, scopes = ls.check(REPO / "uv.lock", snapshot, policy, exceptions)
    assert problems == []
    assert {v.name: v.problems for v in verdicts if v.status == "FAIL"} == {}
    # ADR-048: base and supported extras are proprietary-free.
    for v in verdicts:
        if v.spdx and ("NVIDIA" in v.spdx or "Proprietary" in v.spdx):
            assert v.scopes == ["gpu-frozen"], v
    assert set(scopes) == {"base", "supported-extras", "gpu-frozen"}
