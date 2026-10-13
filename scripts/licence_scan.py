#!/usr/bin/env python3
"""The dependency licence scan over ``uv.lock`` (CONSTITUTION Invariant 5; ADR-048; Stage 21).

Stdlib only; run it as ``python3 -I``. Nothing is ever built or installed.

    check    [--report FILE] [--summary-md FILE]    offline and deterministic (the required check)
    closure  [--scope S | --all-extras] [--compare-export FILE]
    refresh  [--verify]                              online: rebuild (or, with --verify, re-check)
                                                     ci/licence/metadata-snapshot.json

``check`` proceeds in five steps:

1. It computes each scope's dependency closure from the lock. The walk is universal: markers are
   ignored, so every platform's packages are covered.
2. It reads each package's licence metadata from the committed snapshot. Each snapshot entry is
   bound to the lock's exact name, version, source and artifact sha256.
3. It normalises each package along the ADR-048 ladder:
   1. ``License-Expression``;
   2. then a single-line ``License`` field;
   3. then one specific ``License ::`` classifier.

   Anything ambiguous or contradictory is UNKNOWN.
4. It evaluates the SPDX expression against the scope's allowlist.
5. It applies the reviewed exceptions in ``ci/licence/exceptions.toml``. An exception that is
   stale, unneeded or used outside its scopes fails.

``refresh`` reads PEP 658 ``.metadata`` files and verifies each against the PEP 691 core-metadata
sha256. For an sdist-only package it reads ``PKG-INFO`` from the sdist in memory, after checking
the sdist's sha256 against the lock.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import email.parser
import fnmatch
import hashlib
import io
import json
import re
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = REPO / "uv.lock"
LICENCE_DIR = REPO / "ci" / "licence"
SNAPSHOT_FORMAT = 1
INDEX = "https://pypi.org/simple"

BSD_FAMILY = "LicenseRef-OSI-BSD-family"
PROPRIETARY = "LicenseRef-Proprietary"

# Deprecated SPDX ids and ``X+`` forms, mapped to their current ids.
_DEPRECATED = {
    "GPL-2.0": "GPL-2.0-only",
    "GPL-3.0": "GPL-3.0-only",
    "LGPL-2.0": "LGPL-2.0-only",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL-3.0": "LGPL-3.0-only",
    "AGPL-3.0": "AGPL-3.0-only",
}

# Single-line ``License`` field values seen in the wild, mapped to SPDX (case-insensitive).
_LICENSE_TEXT = {
    "mit": "MIT",
    "mit license": "MIT",
    "the mit license": "MIT",
    "mit-cmu": "MIT-CMU",
    "bsd": BSD_FAMILY,
    "bsd license": BSD_FAMILY,
    "new bsd": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd-3": "BSD-3-Clause",
    "3-clause bsd": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "modified bsd": "BSD-3-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "simplified bsd": "BSD-2-Clause",
    "apache": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache software license 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0",
    "isc": "ISC",
    "isc license": "ISC",
    "psf": "PSF-2.0",
    "psf license": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "mpl 2.0": "MPL-2.0",
    "mpl-2.0": "MPL-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "zpl 2.1": "ZPL-2.1",
    "zpl-2.1": "ZPL-2.1",
    "zope public license": "ZPL-2.1",
    "lgpl": None,  # which LGPL? ambiguous on purpose
    "gplv3": "GPL-3.0-only",
    "gplv3+": "GPL-3.0-or-later",
    "lgplv3": "LGPL-3.0-only",
    "lgplv3+": "LGPL-3.0-or-later",
    "lgpl-2.1+": "LGPL-2.1-or-later",
    "zlib": "Zlib",
    "unlicense": "Unlicense",
    "the unlicense": "Unlicense",
    "cc0": "CC0-1.0",
    "boost software license 1.0": "BSL-1.0",
    "hpnd": "HPND",
    "nvidia proprietary software": "LicenseRef-NVIDIA-Proprietary",
}

# Specific ``License ::`` classifiers, mapped to SPDX. Bare ``License :: OSI Approved`` says nothing.
_CLASSIFIER = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: MIT No Attribution License (MIT-0)": "MIT-0",
    "License :: OSI Approved :: BSD License": BSD_FAMILY,
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Zope Public License": "ZPL-2.1",
    "License :: OSI Approved :: zlib/libpng License": "Zlib",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "License :: OSI Approved :: Boost Software License 1.0 (BSL-1.0)": "BSL-1.0",
    "License :: OSI Approved :: Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
    "License :: OSI Approved :: GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)": "GPL-2.0-or-later",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)": "LGPL-2.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.0-or-later",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "License :: OSI Approved :: Eclipse Public License 1.0 (EPL-1.0)": "EPL-1.0",
    "License :: OSI Approved :: Eclipse Public License 2.0 (EPL-2.0)": "EPL-2.0",
    "License :: Other/Proprietary License": PROPRIETARY,
}
_GENERIC_CLASSIFIERS = {"License :: OSI Approved", "License :: Freely Distributable"}

# SPDX ids a free-text ``License`` field may name. (A PEP 639 ``License-Expression`` is validated by
# the build backend and the index, so any syntactically valid id is accepted there; an id that is
# not on the allowlist then simply fails the allowlist.) Anything else in a ``License`` field, such as
# "GPL", "LGPL with exceptions" or "Dual License", is not an id: UNKNOWN, and needs an exception.
_KNOWN_IDS = frozenset(
    {
        "0BSD",
        "AFL-2.1",
        "AFL-3.0",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "Apache-1.1",
        "Apache-2.0",
        "Artistic-2.0",
        "BlueOak-1.0.0",
        "BSD-1-Clause",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSD-4-Clause",
        "BSL-1.0",
        "BUSL-1.1",
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "CC0-1.0",
        "CDDL-1.0",
        "CNRI-Python",
        "curl",
        "ECL-2.0",
        "EPL-1.0",
        "EPL-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "HPND",
        "ISC",
        "LGPL-2.0-only",
        "LGPL-2.0-or-later",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "MIT",
        "MIT-0",
        "MIT-CMU",
        "MPL-1.1",
        "MPL-2.0",
        "MS-PL",
        "NCSA",
        "OFL-1.1",
        "OpenSSL",
        "PostgreSQL",
        "PSF-2.0",
        "Python-2.0",
        "Python-2.0.1",
        "SSPL-1.0",
        "Unicode-3.0",
        "Unicode-DFS-2016",
        "Unlicense",
        "WTFPL",
        "X11",
        "Zlib",
        "ZPL-2.1",
        "LLVM-exception",
        "GCC-exception-2.0",
        "GCC-exception-3.1",
        "Classpath-exception-2.0",
    }
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*\+?$")
_REF_RE = re.compile(r"^(DocumentRef-[A-Za-z0-9.\-]+:)?LicenseRef-[A-Za-z0-9.\-]+$")


# --------------------------------------------------------------------------------------------
# SPDX expressions
# --------------------------------------------------------------------------------------------


class SpdxError(ValueError):
    pass


def _tokens(expr: str) -> list[str]:
    return re.findall(r"\(|\)|[^\s()]+", expr)


def parse_spdx(expr: str) -> Any:
    """Parse an SPDX expression into nested tuples. Precedence: WITH > AND > OR."""
    toks = _tokens(expr)
    pos = 0

    def peek() -> str | None:
        return toks[pos] if pos < len(toks) else None

    def take() -> str:
        nonlocal pos
        if pos >= len(toks):
            raise SpdxError(f"unexpected end of {expr!r}")
        pos += 1
        return toks[pos - 1]

    def atom() -> Any:
        tok = take()
        if tok == "(":
            inner = or_expr()
            if take() != ")":
                raise SpdxError(f"unbalanced parenthesis in {expr!r}")
            return inner
        if tok.upper() in {"AND", "OR", "WITH", ")"}:
            raise SpdxError(f"unexpected {tok!r} in {expr!r}")
        if not (_ID_RE.match(tok) or _REF_RE.match(tok)):
            raise SpdxError(f"{tok!r} is not an SPDX id in {expr!r}")
        lic = tok
        if lic.endswith("+"):
            lic = lic[:-1] + "-or-later"
        lic = _DEPRECATED.get(lic, lic)
        if (peek() or "").upper() == "WITH":
            take()
            exc = take()
            if not _ID_RE.match(exc):
                raise SpdxError(f"{exc!r} is not an exception id in {expr!r}")
            return ("WITH", lic, exc)
        return ("ID", lic)

    def and_expr() -> Any:
        node = atom()
        while (peek() or "").upper() == "AND":
            take()
            node = ("AND", node, atom())
        return node

    def or_expr() -> Any:
        node = and_expr()
        while (peek() or "").upper() == "OR":
            take()
            node = ("OR", node, and_expr())
        return node

    tree = or_expr()
    if pos != len(toks):
        raise SpdxError(f"trailing tokens in {expr!r}")
    return tree


def spdx_ids(tree: Any) -> set[str]:
    if tree[0] == "ID":
        return {tree[1]}
    if tree[0] == "WITH":
        return {f"{tree[1]} WITH {tree[2]}"}
    return spdx_ids(tree[1]) | spdx_ids(tree[2])


def render(tree: Any) -> str:
    if tree[0] == "ID":
        return str(tree[1])
    if tree[0] == "WITH":
        return f"{tree[1]} WITH {tree[2]}"
    left, right = render(tree[1]), render(tree[2])
    if tree[0] == "AND":
        left = f"({left})" if tree[1][0] == "OR" else left
        right = f"({right})" if tree[2][0] == "OR" else right
    return f"{left} {tree[0]} {right}"


def allowed(tree: Any, allow: Callable[[str], bool]) -> bool:
    if tree[0] in {"ID", "WITH"}:
        return allow(spdx_ids(tree).pop())
    if tree[0] == "AND":
        return allowed(tree[1], allow) and allowed(tree[2], allow)
    return allowed(tree[1], allow) or allowed(tree[2], allow)


# --------------------------------------------------------------------------------------------
# The lock and its closures
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LockedPackage:
    name: str
    version: str
    source: str  # "registry", "git+<url>", "editable"
    hashes: frozenset[str]
    wheels: tuple[tuple[str, str], ...]  # (url, sha256), sorted by filename
    sdist: tuple[str, str] | None
    deps: tuple[tuple[str, tuple[str, ...]], ...]
    optional: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = field(hash=False)


def _source(src: dict[str, str]) -> str:
    if "registry" in src:
        return "registry"
    if "git" in src:
        return f"git+{src['git']}"
    if "editable" in src:
        return "editable"
    raise SystemExit(f"unsupported lock source {src}")


def _deps(entries: Iterable[dict[str, Any]]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(sorted((d["name"], tuple(sorted(d.get("extra", ())))) for d in entries))


def _sha256_of(name: str) -> Callable[[str], str]:
    def digest(h: str) -> str:
        algo, _, value = h.partition(":")
        if algo != "sha256":
            raise SystemExit(f"{name}: non-sha256 hash {h}")
        return value

    return digest


def load_lock(path: Path) -> tuple[LockedPackage, dict[str, LockedPackage], bytes]:
    raw = path.read_bytes()
    doc = tomllib.loads(raw.decode("utf-8"))
    packages: dict[str, LockedPackage] = {}
    root: LockedPackage | None = None
    for p in doc["package"]:
        _sha = _sha256_of(p["name"])
        wheels = tuple(
            sorted(
                ((w["url"], _sha(w["hash"])) for w in p.get("wheels", [])),
                key=lambda w: w[0].rsplit("/", 1)[-1],
            )
        )
        sdist = (
            (p["sdist"]["url"], _sha(p["sdist"]["hash"]))
            if "sdist" in p and "url" in p["sdist"]
            else None
        )
        pkg = LockedPackage(
            name=p["name"],
            version=p.get("version", ""),
            source=_source(p["source"]),
            hashes=frozenset([h for _, h in wheels] + ([sdist[1]] if sdist else [])),
            wheels=wheels,
            sdist=sdist,
            deps=_deps(p.get("dependencies", [])),
            optional={k: _deps(v) for k, v in p.get("optional-dependencies", {}).items()},
        )
        if pkg.name in packages:
            raise SystemExit(
                f"{pkg.name} is locked twice (forked resolution is not supported here)"
            )
        packages[pkg.name] = pkg
        if pkg.source == "editable":
            root = pkg
    if root is None:
        raise SystemExit("no editable root package in the lock")
    return root, packages, raw


def closure(
    packages: dict[str, LockedPackage], roots: Iterable[tuple[str, tuple[str, ...]]], root_name: str
) -> set[str]:
    """Every package reachable from ``roots`` (name, extras), ignoring markers (universal)."""
    seen: set[tuple[str, str | None]] = set()
    stack: list[tuple[str, str | None]] = []
    for name, extras in roots:
        stack.append((name, None))
        stack.extend((name, e) for e in extras)
    out: set[str] = set()
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        name, extra = node
        if name == root_name and extra is None:
            continue  # the project itself: its base deps are the base scope, not this one
        if name not in packages:
            raise SystemExit(f"the lock names {name!r} as a dependency but does not lock it")
        pkg = packages[name]
        if name != root_name:
            out.add(name)
        entries = pkg.deps if extra is None else pkg.optional.get(extra, ())
        if extra is not None and extra not in pkg.optional:
            raise SystemExit(
                f"{name}[{extra}] is requested but {name} has no such extra in the lock"
            )
        for dep, dep_extras in entries:
            stack.append((dep, None))
            stack.extend((dep, e) for e in dep_extras)
    return out


def scope_closures(
    root: LockedPackage, packages: dict[str, LockedPackage], policy: dict[str, Any]
) -> dict[str, set[str]]:
    extras_in_lock = set(root.optional)
    claimed: dict[str, str] = {}
    for scope, spec in policy["scopes"].items():
        for extra in spec.get("extras", []):
            if extra in claimed:
                raise SystemExit(f"extra {extra!r} is in scopes {claimed[extra]!r} and {scope!r}")
            claimed[extra] = scope
    if set(claimed) != extras_in_lock:
        raise SystemExit(
            f"every locked extra must be in exactly one scope: unscoped {sorted(extras_in_lock - set(claimed))}, "
            f"unknown {sorted(set(claimed) - extras_in_lock)}"
        )
    out: dict[str, set[str]] = {}
    for scope, spec in policy["scopes"].items():
        if spec.get("base", False):
            roots = list(root.deps)
        else:
            roots = [r for e in spec["extras"] for r in root.optional[e]]
        out[scope] = closure(packages, roots, root.name)
    return out


# --------------------------------------------------------------------------------------------
# Normalisation (the ADR-048 ladder)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Normalised:
    spdx: str | None  # canonical expression, or None = UNKNOWN
    how: str
    problem: str | None = None


def _try_spdx(text: str, *, known_only: bool = False) -> str | None:
    try:
        tree = parse_spdx(text)
    except SpdxError:
        return None
    if known_only:
        for term in spdx_ids(tree):
            for part in term.split(" WITH "):
                if part not in _KNOWN_IDS and not _REF_RE.match(part):
                    return None
    return render(tree)


def _compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    pair = {a, b}
    if PROPRIETARY in pair:
        # The generic "Other/Proprietary" classifier is consistent with a vendor's own LicenseRef.
        other = (pair - {PROPRIETARY}).pop()
        return bool(_REF_RE.match(other))
    return BSD_FAMILY in pair and bool(
        {"BSD-2-Clause", "BSD-3-Clause", "BSD-1-Clause", "0BSD"} & pair
    )


def normalise(entry: dict[str, Any]) -> Normalised:
    if entry.get("license_expression"):
        expr = _try_spdx(entry["license_expression"])
        if expr is None:
            return Normalised(
                None, "License-Expression", f"unparseable {entry['license_expression']!r}"
            )
        return Normalised(expr, "License-Expression")
    from_field: str | None = None
    lic = entry.get("license")
    if lic and lic.strip().upper() not in {"", "UNKNOWN", "NONE"}:
        mapped = _LICENSE_TEXT.get(lic.strip().lower(), "?")
        if mapped == "?":
            mapped = _try_spdx(lic.strip(), known_only=True)
        if mapped is None:
            return Normalised(None, "License", f"License field {lic!r} is not a recognised licence")
        from_field = mapped
    specific = sorted({c for c in entry.get("classifiers", []) if c not in _GENERIC_CLASSIFIERS})
    mapped_cls = {_CLASSIFIER.get(c) for c in specific}
    from_cls: str | None = None
    if specific:
        if None in mapped_cls:
            unknown = [c for c in specific if c not in _CLASSIFIER]
            if from_field is None:
                return Normalised(None, "classifier", f"unmapped classifier(s) {unknown}")
        elif len(mapped_cls) == 1:
            from_cls = mapped_cls.pop()
        elif from_field is None:
            return Normalised(None, "classifier", f"several licence classifiers {specific}")
    if from_field is not None:
        if from_cls is not None and not _compatible(from_field, from_cls):
            return Normalised(
                None, "License+classifier", f"License {lic!r} contradicts classifier {specific}"
            )
        return Normalised(from_field, "License")
    if from_cls is not None:
        return Normalised(from_cls, "classifier")
    if entry.get("license_multiline"):
        return Normalised(None, "License", "the License field holds licence text, not an id")
    return Normalised(None, "none", "no licence metadata")


# --------------------------------------------------------------------------------------------
# Policy, exceptions, the check
# --------------------------------------------------------------------------------------------


def _scope_allows(policy: dict[str, Any], scope: str) -> Callable[[str], bool]:
    allow = set(policy["allow"]) | set(policy.get("allow_with", []))
    patterns = policy["scopes"][scope].get("allow_patterns", [])

    def ok(lic: str) -> bool:
        return lic in allow or any(fnmatch.fnmatchcase(lic, p) for p in patterns)

    return ok


@dataclass
class Verdict:
    name: str
    version: str
    scopes: list[str]
    spdx: str | None
    how: str
    status: str  # allowed | identified-by-exception | admitted-by-exception | FAIL
    problems: list[str]


def check(
    lock: Path, snapshot: dict[str, Any], policy: dict[str, Any], exceptions: list[dict[str, Any]]
) -> tuple[list[Verdict], list[str], dict[str, set[str]]]:
    root, packages, _ = load_lock(lock)
    scopes = scope_closures(root, packages, policy)
    owners: dict[str, list[str]] = {}
    for scope, names in scopes.items():
        for n in names:
            owners.setdefault(n, []).append(scope)
    global_problems: list[str] = []
    orphans = set(packages) - set(owners) - {root.name}
    if orphans:
        global_problems.append(f"locked but unreachable from any scope: {sorted(orphans)}")
    entries = snapshot.get("packages", {})
    if snapshot.get("format") != SNAPSHOT_FORMAT:
        global_problems.append(f"snapshot format {snapshot.get('format')!r} != {SNAPSHOT_FORMAT}")
    stale = sorted(set(entries) - set(owners))
    if stale:
        global_problems.append(
            f"snapshot entries for packages not in the lock: {stale} (run `refresh`)"
        )
    by_key = {}
    for exc in exceptions:
        key = (exc["package"], exc["version"])
        if key in by_key:
            global_problems.append(f"two exceptions for {key}")
        by_key[key] = exc
    used: set[tuple[str, str]] = set()
    verdicts: list[Verdict] = []
    for name in sorted(owners):
        pkg = packages[name]
        problems: list[str] = []
        entry = entries.get(name)
        if entry is None:
            verdicts.append(
                Verdict(
                    name,
                    pkg.version,
                    owners[name],
                    None,
                    "-",
                    "FAIL",
                    ["no snapshot entry (run `refresh`)"],
                )
            )
            continue
        if entry["version"] != pkg.version or entry["source"] != pkg.source:
            problems.append(
                f"snapshot is for {entry['version']} from {entry['source']} (run `refresh`)"
            )
        if pkg.source == "registry" and entry.get("artifact_sha256") not in pkg.hashes:
            problems.append(
                "snapshot artifact sha256 is not one of the lock's hashes (run `refresh`)"
            )
        norm = (
            normalise(entry)
            if pkg.source == "registry"
            else Normalised(None, "none", "a git source has no index metadata")
        )
        exc = by_key.get((name, pkg.version))
        status = "allowed"
        spdx = norm.spdx
        if exc is not None:
            used.add((name, pkg.version))
            if exc.get("commit") and not pkg.source.endswith(exc["commit"]):
                problems.append(
                    f"exception is for commit {exc['commit']}, the lock has {pkg.source}"
                )
            outside = sorted(set(owners[name]) - set(exc["scopes"]))
            if outside:
                problems.append(f"exception does not cover scope(s) {outside}")
            reviewed = _try_spdx(exc["reviewed_spdx"])
            if reviewed is None:
                problems.append(f"exception reviewed_spdx {exc['reviewed_spdx']!r} does not parse")
            elif exc["kind"] == "identify":
                if norm.spdx is not None:
                    problems.append(
                        f"unneeded 'identify' exception: the metadata already says {norm.spdx}"
                    )
                spdx, status = reviewed, "identified-by-exception"
            elif exc["kind"] == "admit":
                spdx, status = reviewed, "admitted-by-exception"
            else:
                problems.append(f"unknown exception kind {exc['kind']!r}")
        if spdx is None:
            problems.append(f"UNKNOWN licence: {norm.problem}")
        elif status != "admitted-by-exception":
            tree = parse_spdx(spdx)
            for scope in owners[name]:
                if not allowed(tree, _scope_allows(policy, scope)):
                    problems.append(f"{spdx} is not allowed in scope {scope!r}")
        else:
            tree = parse_spdx(spdx)
            if all(allowed(tree, _scope_allows(policy, s)) for s in owners[name]):
                problems.append(f"unneeded 'admit' exception: {spdx} is allowed in {owners[name]}")
        verdicts.append(
            Verdict(
                name,
                pkg.version,
                owners[name],
                spdx,
                norm.how,
                "FAIL" if problems else status,
                problems,
            )
        )
    for key in sorted(set(by_key) - used):
        global_problems.append(
            f"unused exception {key[0]}=={key[1]} (stale: the lock moved, or the package left)"
        )
    for exc in exceptions:
        for required in (
            "package",
            "version",
            "kind",
            "scopes",
            "reviewed_spdx",
            "reason",
            "adr",
            "evidence",
            "reviewer",
            "date",
        ):
            if not exc.get(required):
                global_problems.append(f"exception {exc.get('package')!r} lacks {required!r}")
        if not str(exc.get("evidence", "")).startswith("https://"):
            global_problems.append(
                f"exception {exc.get('package')!r}: evidence must be an https URL"
            )
    return verdicts, global_problems, scopes


def _report(verdicts: list[Verdict], problems: list[str], lock_raw: bytes) -> dict[str, Any]:
    return {
        "lock_sha256": hashlib.sha256(lock_raw).hexdigest(),
        "problems": problems,
        "packages": [v.__dict__ for v in verdicts],
        "summary": {
            status: sum(v.status == status for v in verdicts)
            for status in ("allowed", "identified-by-exception", "admitted-by-exception", "FAIL")
        },
    }


def _summary_md(verdicts: list[Verdict], problems: list[str], scopes: dict[str, set[str]]) -> str:
    lines = ["## Dependency licence scan — Invariant 5 (ADR-048)", ""]
    failed = [v for v in verdicts if v.status == "FAIL"]
    lines.append(
        f"**{'FAIL' if failed or problems else 'PASS'}** — {len(verdicts)} locked packages."
    )
    lines.append("")
    lines.append("| scope | packages |")
    lines.append("|---|---|")
    lines.extend(f"| {s} | {len(n)} |" for s, n in scopes.items())
    for title, pick in (
        ("Failures", lambda v: v.status == "FAIL"),
        ("Exceptions", lambda v: v.status.endswith("by-exception")),
        ("BSD family (classifier does not say which clause count)", lambda v: v.spdx == BSD_FAMILY),
        (
            "NVIDIA / proprietary (gpu-frozen only)",
            lambda v: bool(v.spdx and "LicenseRef-NVIDIA" in v.spdx),
        ),
    ):
        rows = [v for v in verdicts if pick(v)]
        if rows:
            lines += [
                "",
                f"### {title}",
                "",
                "| package | version | scopes | licence | status |",
                "|---|---|---|---|---|",
            ]
            lines += [
                f"| {v.name} | {v.version} | {', '.join(v.scopes)} | {v.spdx or '?'} | {v.status}"
                f"{': ' + '; '.join(v.problems) if v.problems else ''} |"
                for v in rows
            ]
    if problems:
        lines += ["", "### Lock-level problems", ""] + [f"- {p}" for p in problems]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------
# Refresh (online): PEP 691 index JSON + PEP 658 metadata, hash-verified
# --------------------------------------------------------------------------------------------

Fetch = Callable[[str, str | None], bytes]


def _urlopen(url: str, accept: str | None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "aero-licence-scan/1"})
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=60) as resp:  # the https index only
        return resp.read()


def _metadata_fields(raw: bytes) -> dict[str, Any]:
    msg = email.parser.Parser().parsestr(raw.decode("utf-8"), headersonly=True)
    lic = msg.get("License")
    lic_text = None if lic is None else str(lic)
    single = lic_text is not None and "\n" not in lic_text.strip()
    return {
        "metadata_version": msg.get("Metadata-Version"),
        "license_expression": msg.get("License-Expression"),
        "license": lic_text.strip() if single and lic_text is not None else None,
        "license_multiline": bool(lic_text and not single),
        "license_text_sha256": hashlib.sha256(lic_text.encode()).hexdigest()
        if lic_text and not single
        else None,
        "classifiers": sorted(
            c for c in msg.get_all("Classifier", []) if c.startswith("License ::")
        ),
    }


def _pkg_info_from_sdist(name: str, data: bytes) -> bytes:
    candidates: dict[str, bytes] = {}
    if data[:2] == b"\x1f\x8b":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.count("/") == 1 and m.name.endswith("/PKG-INFO"):
                    fh = tf.extractfile(m)
                    if fh is not None:
                        candidates[m.name] = fh.read()
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for n in zf.namelist():
                if n.count("/") == 1 and n.endswith("/PKG-INFO"):
                    candidates[n] = zf.read(n)
    if len(candidates) != 1:
        raise SystemExit(f"{name}: the sdist has {len(candidates)} top-level PKG-INFO files")
    return next(iter(candidates.values()))


def _refresh_one(pkg: LockedPackage, fetch: Fetch) -> dict[str, Any]:
    base: dict[str, Any] = {"version": pkg.version, "source": pkg.source}
    if pkg.source != "registry":
        return {**base, "artifact": None, "artifact_sha256": None, "metadata_sha256": None}
    index = json.loads(fetch(f"{INDEX}/{pkg.name}/", "application/vnd.pypi.simple.v1+json"))
    files = {f["filename"]: f for f in index["files"]}
    for url, sha in pkg.wheels:
        fname = url.rsplit("/", 1)[-1]
        f = files.get(fname)
        if f is None or f.get("hashes", {}).get("sha256") != sha:
            continue
        cm = f.get("core-metadata") or f.get("data-dist-info-metadata")
        if not isinstance(cm, dict) or "sha256" not in cm:
            continue
        raw = fetch(f["url"] + ".metadata", None)
        if hashlib.sha256(raw).hexdigest() != cm["sha256"]:
            raise SystemExit(f"{pkg.name}: {fname}.metadata does not match its PEP 691 hash")
        return {
            **base,
            "artifact": fname,
            "artifact_sha256": sha,
            "metadata_sha256": cm["sha256"],
            **_metadata_fields(raw),
        }
    if pkg.sdist is None:
        raise SystemExit(f"{pkg.name}: no wheel with PEP 658 metadata and no sdist")
    url, sha = pkg.sdist
    data = fetch(url, None)
    if hashlib.sha256(data).hexdigest() != sha:
        raise SystemExit(f"{pkg.name}: the sdist does not match the lock's sha256")
    raw = _pkg_info_from_sdist(pkg.name, data)
    return {
        **base,
        "artifact": url.rsplit("/", 1)[-1],
        "artifact_sha256": sha,
        "metadata_sha256": hashlib.sha256(raw).hexdigest(),
        **_metadata_fields(raw),
    }


def refresh(lock: Path, fetch: Fetch = _urlopen, workers: int = 16) -> dict[str, Any]:
    _, packages, _ = load_lock(lock)
    todo = [p for p in packages.values() if p.source != "editable"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(
            zip(
                [p.name for p in todo],
                pool.map(lambda p: _refresh_one(p, fetch), todo),
                strict=True,
            )
        )
    return {"format": SNAPSHOT_FORMAT, "index": INDEX, "packages": dict(sorted(results.items()))}


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def _load_inputs(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    policy = tomllib.loads(Path(args.policy).read_text(encoding="utf-8"))
    exceptions = tomllib.loads(Path(args.exceptions).read_text(encoding="utf-8")).get(
        "exception", []
    )
    return snapshot, policy, exceptions


def _export_names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", "--")):
            continue
        names.add(re.split(r"[ =<>!~;@\[]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    ap.add_argument("--snapshot", type=Path, default=LICENCE_DIR / "metadata-snapshot.json")
    ap.add_argument("--policy", type=Path, default=LICENCE_DIR / "policy.toml")
    ap.add_argument("--exceptions", type=Path, default=LICENCE_DIR / "exceptions.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--report", type=Path)
    c.add_argument("--summary-md", type=Path)
    cl = sub.add_parser("closure")
    cl.add_argument("--scope")
    cl.add_argument("--all-extras", action="store_true")
    cl.add_argument(
        "--compare-export", type=Path, help="a `uv export --format requirements.txt` file"
    )
    r = sub.add_parser("refresh")
    r.add_argument("--verify", action="store_true", help="re-fetch and compare; write nothing")
    a = ap.parse_args(argv)

    if a.cmd == "refresh":
        fresh = refresh(a.lock)
        if a.verify:
            committed = json.loads(a.snapshot.read_text(encoding="utf-8"))
            if committed != fresh:
                drift = sorted(
                    n
                    for n in set(committed["packages"]) | set(fresh["packages"])
                    if committed["packages"].get(n) != fresh["packages"].get(n)
                )
                print(f"SNAPSHOT DRIFT vs the index: {drift}", file=sys.stderr)
                return 1
            print(f"snapshot re-verified online: {len(fresh['packages'])} packages")
            return 0
        a.snapshot.parent.mkdir(parents=True, exist_ok=True)
        a.snapshot.write_text(_dump(fresh), encoding="utf-8", newline="\n")
        print(f"wrote {a.snapshot} ({len(fresh['packages'])} packages)")
        return 0

    snapshot, policy, exceptions = _load_inputs(a)
    if a.cmd == "closure":
        root, packages, _ = load_lock(a.lock)
        scopes = scope_closures(root, packages, policy)
        names = (
            set().union(*scopes.values()) if a.all_extras or a.scope is None else scopes[a.scope]
        )
        if a.compare_export is not None:
            exported = _export_names(a.compare_export)
            if exported != names:
                print(
                    f"CLOSURE != uv export: only here {sorted(names - exported)}, "
                    f"only in the export {sorted(exported - names)}",
                    file=sys.stderr,
                )
                return 1
            print(f"closure == uv export ({len(names)} packages)")
            return 0
        print("\n".join(sorted(names)))
        return 0

    verdicts, problems, scopes = check(a.lock, snapshot, policy, exceptions)
    _, _, raw = load_lock(a.lock)
    if a.report is not None:
        a.report.write_text(_dump(_report(verdicts, problems, raw)), encoding="utf-8", newline="\n")
    if a.summary_md is not None:
        with a.summary_md.open("a", encoding="utf-8") as fh:
            fh.write(_summary_md(verdicts, problems, scopes))
    for v in verdicts:
        if v.status == "FAIL":
            print(
                f"FAIL  {v.name}=={v.version} [{', '.join(v.scopes)}]: {'; '.join(v.problems)}",
                file=sys.stderr,
            )
    for p in problems:
        print(f"FAIL  {p}", file=sys.stderr)
    counts = _report(verdicts, problems, raw)["summary"]
    print(f"{len(verdicts)} packages: " + ", ".join(f"{k} {n}" for k, n in counts.items()))
    return 1 if problems or counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
