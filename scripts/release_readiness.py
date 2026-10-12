#!/usr/bin/env python3
"""Is the repository ready to tag a release? (ADR-049 R2; Stage 21). Stdlib only: ``python3 -I``.

    python3 -I scripts/release_readiness.py --gate release [--online]          before tagging
    python3 -I scripts/release_readiness.py --gate release --ci --tag vX.Y.Z --online   on tag push
    python3 -I scripts/release_readiness.py --gate joss [--online]             before JOSS submission

Every check prints PASS or FAIL with its reasons; exit 1 if anything fails. "All required CI green"
is verified here, not assumed (enforce_admins is off and a PR once merged red). Every context
registered in .github/required-checks.json must have concluded ``success``:
- on the release commit, for push contexts;
- on the merged PR's head, for PR-only contexts. That head must have the same tree.

Skipped, neutral, cancelled or missing counts as NOT green. ``--online`` uses the GitHub REST API,
with ``GH_TOKEN`` if set. It never prints the token.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
GH_REPO_DEFAULT = "ernesto01louis/aero-research-platform"

L1 = "The optimizer has never been run on a flapping-wing case, and v0.1.0 makes no flapping-wing optimization claim."
FLAGSHIP_S3 = "No flapping optimization claim is made in v0.1.0."
# Record-faithful phrases the release notes must carry in their body (operator decision D2).
RELEASE_NOTE_PHRASES = (
    L1,
    "a pre-registered, non-gated diagnostic",
    "45.7 %",
    "the band was not relaxed",
    "the leading hypothesis",
    "degenerate",
)
FORBIDDEN_PHRASES = (
    "root-caused",
    "+47",
    "thesis-grade improvement",
    "certified optimum",
    "topology optimizer",
    "neural operator",
    "Surrogates accelerate",
    "validated ensemble drove",
    "pip install aero ",
    "pip install aero`",
)
# The Stage-20 sentinels stay unfilled (Stage-21 hard don'ts). Their placeholder homes and counts.
B_SENTINEL_HOMES = {
    "docs/adrs/ADR-040-campaign-numerics-re-preregistration.md": {
        "<<B1-PENDING-N3>>": 2,
        "<<B2-PENDING-ADR040>>": 2,
        "<<B3-PENDING-CEILING>>": 2,
        "<<B2-PENDING-I4>>": 2,
    },
    "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md": {"<<B2-PENDING-I4>>": 1},
}
ADR045_ABSENT = ("data/vv/stage20_adr045_r3.json", "data/vv/stage20_n3_confirmation.json")
STAGE20_EVIDENCE_TAG = "stage-20-evidence-2026-09-20"
INSTALL_DOCS = ("README.md", "CONTRIBUTING.md", "CONSTITUTION.md", "SECURITY.md", "CITATION.cff")
BARE_PIP = re.compile(r"pip install aero(?![-\w])")
CERT_MARGIN = dt.timedelta(days=30)
JOSS_EARLIEST = dt.date(2026, 11, 18)  # repo public 2026-05-17 + 6 months + 1 day
JOSS_HEADINGS = (
    "Summary",
    "Statement of need",
    "State of the field",
    "Software design",
    "Research impact statement",
    "AI usage disclosure",
    "Acknowledgements",
    "References",
)

Api = Callable[[str], Any]


@dataclass
class Ctx:
    repo: Path
    tag: str | None
    ci: bool
    online: bool
    api: Api | None
    today: dt.date
    gh_repo: str


@dataclass
class Result:
    name: str
    problems: list[str]


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _git_ok(repo: Path, *args: str) -> bool:
    return (
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False).returncode == 0
    )


def _read(repo: Path, rel: str) -> str | None:
    p = repo / rel
    return p.read_text(encoding="utf-8") if p.is_file() else None


def _version(repo: Path) -> str:
    return str(
        tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    )


def _cff(repo: Path, key: str) -> str | None:
    text = _read(repo, "CITATION.cff") or ""
    m = re.search(rf"^{re.escape(key)}:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", text, re.M)
    return m.group(1) if m else None


def _body(markdown: str) -> str:
    """The text before Acknowledgements / References, without footnote definitions."""
    cut = re.search(r"^#{1,3}\s+(Acknowledg|References)", markdown, re.M)
    text = markdown[: cut.start()] if cut else markdown
    return "\n".join(line for line in text.splitlines() if not re.match(r"^\[\^[^\]]+\]:", line))


def _urlopen_api(gh_repo: str) -> Api:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def get(path: str) -> Any:
        url = path if path.startswith("https://") else f"https://api.github.com/{path.lstrip('/')}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "aero-release-readiness",
            },
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=60) as resp:  # the GitHub API only
            return json.loads(resp.read())

    return get


# --------------------------------------------------------------------------------------------
# release checks
# --------------------------------------------------------------------------------------------


def check_tree(c: Ctx) -> list[str]:
    if c.ci:
        return []
    out = []
    if _git(c.repo, "status", "--porcelain"):
        out.append("the working tree is not clean")
    if _git_ok(c.repo, "rev-parse", "--verify", "-q", "origin/main"):
        if _git(c.repo, "rev-parse", "HEAD") != _git(c.repo, "rev-parse", "origin/main"):
            out.append("HEAD is not origin/main (tag the merged release commit on main)")
    else:
        out.append("origin/main is unknown (git fetch origin)")
    return out


def check_versions(c: Ctx) -> list[str]:
    out = []
    version = _version(c.repo)
    lock = tomllib.loads((c.repo / "uv.lock").read_text(encoding="utf-8"))
    roots = [p for p in lock["package"] if p.get("source", {}).get("editable") == "."]
    if len(roots) != 1 or roots[0]["version"] != version:
        out.append(
            f"uv.lock root version {[r.get('version') for r in roots]} != pyproject {version}"
        )
    cff = _cff(c.repo, "version")
    if cff != version:
        out.append(f"CITATION.cff version {cff!r} != pyproject {version}")
    if c.tag is not None and c.tag != f"v{version}":
        out.append(f"the tag {c.tag} != v{version}")
    changelog = _read(c.repo, "CHANGELOG.md") or ""
    m = re.search(rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})", changelog, re.M)
    if m is None:
        out.append(f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' heading")
    else:
        released = _cff(c.repo, "date-released")
        if released != m.group(1):
            out.append(
                f"CITATION.cff date-released {released!r} != the CHANGELOG date {m.group(1)}"
            )
        if dt.date.fromisoformat(m.group(1)) > c.today:
            out.append(f"the release date {m.group(1)} is in the future")
    return out


def check_handoff(c: Ctx) -> list[str]:
    if c.ci:
        return []  # tag-handoff-gate.yml runs check_release_tag.sh --ci as its own step
    tag = c.tag or f"v{_version(c.repo)}"
    r = subprocess.run(
        ["bash", str(c.repo / "scripts" / "check_release_tag.sh"), tag, "--pre-tag"],
        cwd=c.repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        []
        if r.returncode == 0
        else [ln.split("FAIL: ", 1)[1] for ln in r.stderr.splitlines() if "FAIL: " in ln]
        or [r.stderr.strip()]
    )


def check_sentinels(c: Ctx) -> list[str]:
    out = []
    for rel in ("CITATION.cff", ".zenodo.json"):
        text = _read(c.repo, rel)
        if text is None:
            out.append(f"{rel} is missing")
        elif "<<OPERATOR-" in text:
            out.append(f"{rel} still carries an <<OPERATOR-...>> sentinel")
    return out


def check_limitation_in_body(c: Ctx) -> list[str]:
    out = []
    version = _version(c.repo)
    notes_rel = f"docs/release/RELEASE-NOTES-v{version}.md"
    for rel, phrases in ((notes_rel, RELEASE_NOTE_PHRASES), ("paper/paper.md", (L1,))):
        text = _read(c.repo, rel)
        if text is None:
            out.append(f"{rel} is missing")
            continue
        body = _body(text)
        out += [f"{rel}: the body lacks {p!r}" for p in phrases if p not in body]
        out += [f"{rel}: forbidden phrase {p!r}" for p in FORBIDDEN_PHRASES if p in text]
    return out


def check_licence_scan(c: Ctx) -> list[str]:
    script = c.repo / "scripts" / "licence_scan.py"
    if not script.is_file():
        return ["scripts/licence_scan.py is missing (Invariant 5's scan)"]
    r = subprocess.run(
        [sys.executable, "-I", str(script), "check"],
        cwd=c.repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return [] if r.returncode == 0 else [f"licence scan: {ln}" for ln in r.stderr.splitlines()[:10]]


def check_crates(c: Ctx) -> list[str]:
    crates = sorted(p for p in (c.repo / "crates").glob("stage*/aero-crate.json"))
    if not crates:
        return ["no crates under crates/ (Hard Rule 16 / Invariant 13)"]
    out = []
    now = dt.datetime.combine(c.today, dt.time(), tzinfo=dt.UTC)
    for path in crates:
        m = json.loads(path.read_text(encoding="utf-8"))
        expiry = m["validity"].get("certificate_expiry")
        if expiry is not None:
            left = dt.datetime.fromisoformat(expiry.replace("Z", "+00:00")) - now
            if left < CERT_MARGIN:
                out.append(
                    f"{m['crate_id']}: the cited certificate expires {expiry} ({left.days} days left, need > 30)"
                )
        if c.online and c.api is not None:
            for run in m["runs"]:
                prov = run["provenance"]
                if prov["status"] == "available" and prov["code"]["publicly_resolvable"]:
                    sha = prov["four_tuple"]["git_sha"]
                    try:
                        c.api(f"repos/{c.gh_repo}/commits/{sha}")
                    except Exception as exc:  # report, do not crash
                        out.append(f"{m['crate_id']}: {sha} does not resolve on GitHub ({exc})")
    return out


def check_install_text(c: Ctx) -> list[str]:
    out = []
    files = [*INSTALL_DOCS, *(str(p.relative_to(c.repo)) for p in (c.repo / "aero").rglob("*.py"))]
    files += [
        str(p.relative_to(c.repo))
        for d in ("docs/release", "paper")
        for p in (c.repo / d).rglob("*.md")
    ]
    for rel in files:
        text = _read(c.repo, rel) or ""
        for n, line in enumerate(text.splitlines(), 1):
            if BARE_PIP.search(line):
                out.append(
                    f"{rel}:{n}: bare `pip install aero` (the name is not ours on PyPI; ADR-049 R3)"
                )
    return out


def check_governance(c: Ctx) -> list[str]:
    out = []
    constitution = _read(c.repo, "CONSTITUTION.md") or ""
    if not re.search(r"^## Invariant 13\b", constitution, re.M):
        out.append("CONSTITUTION.md has no '## Invariant 13' (RESULTS-MUST-TRAVEL is not ratified)")
    for n in (47, 48, 49):
        adr = next((c.repo / "docs" / "adrs").glob(f"ADR-0{n}-*.md"), None)
        text = adr.read_text(encoding="utf-8") if adr else ""
        if not re.search(r"^- \*\*Status:\*\*\s*accepted", text, re.M):
            out.append(f"ADR-0{n} is not accepted")
    return out


def check_tag_state(c: Ctx) -> list[str]:
    tag = c.tag or f"v{_version(c.repo)}"
    exists = _git_ok(c.repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    if c.ci:
        return [] if exists else [f"{tag} does not exist"]
    return [f"{tag} already exists"] if exists else []


def check_hard_donts(c: Ctx) -> list[str]:
    out = [
        f"{rel} exists (an ADR-045 record that must never be created)"
        for rel in ADR045_ABSENT
        if (c.repo / rel).exists()
    ]
    for rel, counts in B_SENTINEL_HOMES.items():
        text = _read(c.repo, rel) or ""
        for sentinel, n in counts.items():
            if text.count(sentinel) != n:
                out.append(
                    f"{rel}: {sentinel} occurs {text.count(sentinel)} times, not {n} (a Stage-20 sentinel moved)"
                )
    if c.online and c.api is not None:
        try:
            c.api(f"repos/{c.gh_repo}/git/ref/tags/{STAGE20_EVIDENCE_TAG}")
        except Exception:
            out.append(f"{STAGE20_EVIDENCE_TAG} is not on origin")
    elif not _git_ok(c.repo, "rev-parse", "-q", "--verify", f"refs/tags/{STAGE20_EVIDENCE_TAG}"):
        out.append(f"{STAGE20_EVIDENCE_TAG} is not a local tag (git fetch --tags)")
    return out


def _check_runs(api: Api, gh_repo: str, sha: str) -> dict[str, str]:
    """Latest conclusion per check-run name on ``sha`` (all pages), plus legacy statuses."""
    runs: dict[str, tuple[str, str]] = {}
    page = 1
    while True:
        doc = api(f"repos/{gh_repo}/commits/{sha}/check-runs?per_page=100&page={page}")
        for r in doc.get("check_runs", []):
            stamp = r.get("completed_at") or r.get("started_at") or ""
            prev = runs.get(r["name"])
            state = r.get("conclusion") or r.get("status") or "missing"
            if prev is None or stamp >= prev[0]:
                runs[r["name"]] = (stamp, state)
        if len(doc.get("check_runs", [])) < 100:
            break
        page += 1
    statuses = api(f"repos/{gh_repo}/commits/{sha}/status")
    for s in statuses.get("statuses", []):
        runs.setdefault(s["context"], ("", s["state"]))
    return {name: state for name, (_, state) in runs.items()}


def check_required_contexts(c: Ctx) -> list[str]:
    if not c.online or c.api is None:
        return ["skipped: needs --online (required CI is verified, never assumed)"]
    registry = json.loads((c.repo / ".github" / "required-checks.json").read_text(encoding="utf-8"))
    head = _git(c.repo, "rev-parse", "HEAD")
    out = []
    on_head = _check_runs(c.api, c.gh_repo, head)
    pr_heads: dict[str, str] = {}
    pr_only = [e for e in registry["contexts"] if e["pr_only"]]
    if pr_only:
        prs = c.api(f"repos/{c.gh_repo}/commits/{head}/pulls")
        merged = [p for p in prs if p.get("merged_at")]
        if len(merged) != 1:
            out.append(
                f"{len(merged)} merged PRs are associated with {head[:12]}; need exactly one"
            )
        else:
            pr_head = merged[0]["head"]["sha"]
            if not _git_ok(c.repo, "cat-file", "-e", f"{pr_head}^{{commit}}"):
                out.append(
                    f"the PR head {pr_head[:12]} is not fetched (git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*')"
                )
            elif _git(c.repo, "rev-parse", f"{pr_head}^{{tree}}") != _git(
                c.repo, "rev-parse", f"{head}^{{tree}}"
            ):
                out.append(
                    f"the merged PR head {pr_head[:12]} has a different tree from {head[:12]} (PR checks would not cover it)"
                )
            pr_heads = _check_runs(c.api, c.gh_repo, pr_head)
    for entry in registry["contexts"]:
        where = pr_heads if entry["pr_only"] else on_head
        state = where.get(entry["context"], "missing")
        if state != "success":
            out.append(
                f"required context {entry['context']!r} is {state!r} on the {'PR head' if entry['pr_only'] else 'release commit'}"
            )
    return out


# --------------------------------------------------------------------------------------------
# JOSS checks (Stage 21 ends at "ready to submit"; the operator submits)
# --------------------------------------------------------------------------------------------


def check_joss_date(c: Ctx) -> list[str]:
    return (
        []
        if c.today >= JOSS_EARLIEST
        else [f"JOSS needs 6 months of public history: earliest {JOSS_EARLIEST}"]
    )


def check_paper(c: Ctx) -> list[str]:
    paper = _read(c.repo, "paper/paper.md")
    bib = _read(c.repo, "paper/paper.bib")
    if paper is None or bib is None:
        return ["paper/paper.md and paper/paper.bib must both exist"]
    out = []
    front = re.match(r"^---\n(.*?)\n---\n", paper, re.S)
    if front is None:
        return ["paper/paper.md has no YAML front matter"]
    meta, body = front.group(1), paper[front.end() :]
    title = re.search(r"^title:\s*(.+)$", meta, re.M)
    if title is None or "`" in title.group(1):
        out.append("the title is missing or contains backticks")
    date = re.search(r"^date:\s*['\"]?(.+?)['\"]?\s*$", meta, re.M)
    if date is None or not re.fullmatch(r"\d{1,2} [A-Z][a-z]+ \d{4}", date.group(1).strip()):
        out.append("date must look like '%e %B %Y' (e.g. 18 November 2026)")
    if "<<OPERATOR-" in paper:
        out.append("the paper still carries an <<OPERATOR-...>> sentinel")
    words = len(re.findall(r"\b\w[\w'-]*\b", re.sub(r"```.*?```", "", body, flags=re.S)))
    if not 750 <= words <= 1750:
        out.append(f"the paper body has {words} words; JOSS wants 750-1750")
    headings = set(re.findall(r"^#\s+(.+?)\s*$", body, re.M))
    out += [f"missing section '# {h}'" for h in JOSS_HEADINGS if h not in headings]
    keys = set(re.findall(r"@([A-Za-z0-9_:\-]+)", re.sub(r"\S+@\S+\.\S+", "", body)))
    known = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib))
    out += [f"citation @{k} is not in paper.bib" for k in sorted(keys - known)]
    return out


def check_operator_metadata(c: Ctx) -> list[str]:
    text = _read(c.repo, "docs/release/operator-metadata.toml")
    if text is None:
        return ["docs/release/operator-metadata.toml is missing"]
    meta = tomllib.loads(text)
    return [
        f"operator metadata {k!r} is still a sentinel"
        for k, v in sorted(meta.items())
        if isinstance(v, str) and v.startswith("<<OPERATOR-")
    ]


def check_release_published(c: Ctx) -> list[str]:
    version = _version(c.repo)
    zenodo = _read(c.repo, "docs/release/zenodo.md") or ""
    out = (
        []
        if re.search(r"10\.5281/zenodo\.\d+", zenodo.replace("10.5281/zenodo.20292712", ""))
        else ["no version DOI recorded in docs/release/zenodo.md"]
    )
    if c.online and c.api is not None:
        try:
            rel = c.api(f"repos/{c.gh_repo}/releases/tags/v{version}")
            if rel.get("draft") or rel.get("prerelease"):
                out.append(f"the v{version} Release is a draft or pre-release (no DOI is minted)")
        except Exception:
            out.append(f"no published GitHub Release for v{version}")
    return out


def check_ai_inventory(c: Ctx) -> list[str]:
    script = c.repo / "scripts" / "ai_usage_inventory.py"
    if not script.is_file():
        return ["scripts/ai_usage_inventory.py is missing"]
    r = subprocess.run(
        [sys.executable, "-I", str(script), "--check"],
        cwd=c.repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return [] if r.returncode == 0 else [r.stderr.strip() or "ai_usage_inventory --check failed"]


RELEASE_CHECKS: list[tuple[str, Callable[[Ctx], list[str]]]] = [
    ("clean tree at origin/main", check_tree),
    ("versions agree", check_versions),
    ("release handoff gate (--pre-tag)", check_handoff),
    ("no operator sentinels in CITATION / .zenodo.json", check_sentinels),
    ("the ADR-046 limitation is in the BODY of the notes and the paper", check_limitation_in_body),
    ("dependency licence scan (Invariant 5)", check_licence_scan),
    ("crates: certificates > 30 days; SHAs resolve", check_crates),
    ("no bare `pip install aero`", check_install_text),
    ("Invariant 13 ratified; ADR-047/048/049 accepted", check_governance),
    ("tag state", check_tag_state),
    ("hard don'ts", check_hard_donts),
    ("every required context green", check_required_contexts),
]
JOSS_CHECKS: list[tuple[str, Callable[[Ctx], list[str]]]] = [
    *RELEASE_CHECKS[3:9],
    ("six months public", check_joss_date),
    ("paper structure", check_paper),
    ("operator metadata filled", check_operator_metadata),
    ("AI usage inventory", check_ai_inventory),
    ("release published, version DOI recorded", check_release_published),
]


def run(gate: str, c: Ctx) -> list[Result]:
    checks = RELEASE_CHECKS if gate == "release" else JOSS_CHECKS
    results = []
    for name, fn in checks:
        try:
            problems = fn(c)
        except Exception as exc:  # a crashing check is a failing check
            problems = [f"the check crashed: {type(exc).__name__}: {exc}"]
        results.append(Result(name, problems))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gate", choices=("release", "joss"), required=True)
    ap.add_argument("--tag")
    ap.add_argument("--ci", action="store_true", help="on a tag push (tag-handoff-gate.yml)")
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--repo", type=Path, default=REPO)
    a = ap.parse_args(argv)
    gh_repo = os.environ.get("GH_REPO", GH_REPO_DEFAULT)
    c = Ctx(
        repo=a.repo,
        tag=a.tag,
        ci=a.ci,
        online=a.online,
        api=_urlopen_api(gh_repo) if a.online else None,
        today=dt.datetime.now(dt.UTC).date(),
        gh_repo=gh_repo,
    )
    results = run(a.gate, c)
    for r in results:
        print(f"{'PASS' if not r.problems else 'FAIL'}  {r.name}")
        for p in r.problems:
            print(f"        - {p}")
    failed = [r for r in results if r.problems]
    if failed:
        print(f"\nNOT READY: {len(failed)} of {len(results)} checks fail.")
        return 1
    head = _git(c.repo, "rev-parse", "HEAD")
    version = _version(c.repo)
    print(
        f"\nREADY TO TAG v{version} at {head}"
        if a.gate == "release"
        else "\nREADY TO SUBMIT to JOSS"
    )
    if a.gate == "release" and not a.ci:
        print(f"  operator:  git tag -a v{version} {head} -m 'aero-research-platform v{version}'")
        print(f"             git push origin v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
