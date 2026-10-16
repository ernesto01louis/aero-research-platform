"""Workflow hygiene — the CI supply-chain rules of Stage 21 (ADR-049 H-08..H-11, H-19, H-21, H-28, H-32).

Each rule here was broken on main at stage open (2026-10-11) and fixed in the same PR that added
the test, so a later careless edit fails the required ``pytest unit`` job instead of silently
reopening the hole:

* every ``uses:`` is pinned to a full commit SHA with a ``# vX.Y.Z`` comment (mutable tags let an
  upstream re-point what runs, including inside secret-bearing self-hosted jobs);
* hosted jobs run on a pinned image (``ubuntu-24.04``; ``macos-15`` / ``windows-2025`` for
  cross-OS legs), never a moving ``*-latest`` label;
* every workflow declares top-level ``permissions``; every checkout sets
  ``persist-credentials: false``;
* untrusted event text never reaches a ``run:`` script through ``${{ }}`` interpolation;
* repository secrets appear only in STEP ``env`` blocks, never job- or workflow-level;
* every self-hosted job sets ``AERO_RUN_LONG_REAP`` and sits in a concurrency group, and every
  pull-request-triggered self-hosted job except the required ``vv-required`` carries the
  same-repo fork guard;
* every required context in ``.github/required-checks.json`` is reported by exactly one job whose
  rendered name matches byte for byte, and no required workflow has a workflow-level path filter
  (a skipped required check blocks merges forever);
* commitlint has no ``ignores:`` exemption; vv-scale-resolving has no schedule; docs-sync keeps
  ``fetch-depth: 0``; the Dependabot commit prefix names the current stage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS.glob("*.yml"))

_SHA_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
_USES_LINE = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)\s*(#.*)?$")
_UNTRUSTED = re.compile(
    r"\$\{\{\s*github\.(event\.(pull_request\.(title|body|head\.ref|head\.label)|issue|comment|"
    r"review|inputs|head_commit|commits)|head_ref)"
)
_SECRET = re.compile(r"\$\{\{\s*secrets\.")
_FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), path
    # PyYAML (YAML 1.1) parses the bare key `on` as the boolean True.
    if True in data:
        data["on"] = data.pop(True)
    return data


def _triggers(wf: dict[str, Any]) -> dict[str, Any]:
    on = wf.get("on")
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return dict.fromkeys(on)
    assert isinstance(on, dict)
    return on


def _self_hosted(job: dict[str, Any]) -> bool:
    runs_on = job.get("runs-on")
    labels = runs_on if isinstance(runs_on, list) else [runs_on]
    return "self-hosted" in labels


def _render_name(name: str, job: dict[str, Any]) -> list[str]:
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    names = [name]
    for key, values in matrix.items():
        if not isinstance(values, list):
            continue
        token = "${{ matrix." + key + " }}"
        if token in name:
            names = [n.replace(token, str(v)) for n in names for v in values]
    return names


@pytest.fixture(scope="module")
def workflows() -> dict[str, dict[str, Any]]:
    return {p.name: _load(p) for p in WORKFLOW_FILES}


def test_there_are_workflows_to_check() -> None:
    assert len(WORKFLOW_FILES) >= 17


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_every_action_is_sha_pinned_with_a_version_comment(path: Path) -> None:
    for n, line in enumerate(path.read_text().splitlines(), 1):
        m = _USES_LINE.match(line)
        if not m:
            continue
        ref, comment = m.group(1), m.group(2) or ""
        if ref.startswith("./"):
            continue
        assert _SHA_PIN.match(ref), f"{path.name}:{n} is not SHA-pinned: {ref}"
        assert re.match(r"#\s*v\d", comment), f"{path.name}:{n} lacks a '# vX.Y.Z' comment"


# Pinned images only, never the moving `*-latest` labels (ubuntu-latest moves to Ubuntu 26 from
# 2026-10-19). macOS and Windows appear only where a cross-OS leg needs them (crate round-trip).
_HOSTED_IMAGES = {"ubuntu-24.04", "macos-15", "windows-2025"}


def _hosted_images(job: dict[str, Any]) -> list[str]:
    runs_on = job.get("runs-on")
    if isinstance(runs_on, str) and runs_on.startswith("${{ matrix."):
        key = runs_on.removeprefix("${{ matrix.").removesuffix("}}").strip()
        matrix = (job.get("strategy") or {}).get("matrix") or {}
        values = list(matrix.get(key) or [])
        values += [i[key] for i in matrix.get("include", []) if key in i]
        assert values, f"runs-on {runs_on!r} resolves to nothing"
        return [str(v) for v in values]
    return [str(runs_on)]


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_hosted_jobs_use_a_pinned_image(path: Path, workflows: dict[str, Any]) -> None:
    for job_id, job in workflows[path.name]["jobs"].items():
        if _self_hosted(job):
            continue
        for image in _hosted_images(job):
            assert image in _HOSTED_IMAGES, f"{path.name}:{job_id} runs-on {image!r}"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_top_level_permissions_are_declared(path: Path, workflows: dict[str, Any]) -> None:
    assert "permissions" in workflows[path.name], f"{path.name} has no top-level permissions block"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_every_checkout_drops_its_credentials(path: Path, workflows: dict[str, Any]) -> None:
    for job_id, job in workflows[path.name]["jobs"].items():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert (step.get("with") or {}).get("persist-credentials") is False, (
                    f"{path.name}:{job_id}"
                )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_no_untrusted_event_text_is_interpolated_into_a_script(
    path: Path, workflows: dict[str, Any]
) -> None:
    for job_id, job in workflows[path.name]["jobs"].items():
        for step in job.get("steps", []):
            script = step.get("run") or ""
            if "script" in (step.get("with") or {}):
                script += str(step["with"]["script"])
            assert not _UNTRUSTED.search(script), (
                f"{path.name}:{job_id} step {step.get('name')!r} interpolates untrusted event text "
                "into a script; pass it through env instead"
            )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_secrets_are_step_scoped(path: Path, workflows: dict[str, Any]) -> None:
    wf = workflows[path.name]
    assert not _SECRET.search(json.dumps(wf.get("env") or {})), (
        f"{path.name}: workflow-level secret"
    )
    for job_id, job in wf["jobs"].items():
        assert not _SECRET.search(json.dumps(job.get("env") or {})), (
            f"{path.name}:{job_id}: job-level secret"
        )
        for step in job.get("steps", []):
            body = json.dumps({k: v for k, v in step.items() if k != "env"})
            assert not _SECRET.search(body), f"{path.name}:{job_id}: secret outside a step env"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_self_hosted_jobs_reap_and_are_grouped(path: Path, workflows: dict[str, Any]) -> None:
    wf = workflows[path.name]
    for job_id, job in wf["jobs"].items():
        if not _self_hosted(job):
            continue
        assert (job.get("env") or {}).get("AERO_RUN_LONG_REAP") == "1", (
            f"{path.name}:{job_id} lacks REAP"
        )
        assert "concurrency" in wf or "concurrency" in job, (
            f"{path.name}:{job_id} has no concurrency group"
        )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_pull_request_self_hosted_jobs_have_the_fork_guard(
    path: Path, workflows: dict[str, Any]
) -> None:
    wf = workflows[path.name]
    if "pull_request" not in _triggers(wf):
        return
    for job_id, job in wf["jobs"].items():
        if not _self_hosted(job):
            continue
        if path.name == "vv-required.yml":
            # A required check must always report; a skipped job would report success for a fork.
            # Its fork exposure is closed by the operator's fork-approval setting (ADR-049 H-11).
            continue
        assert _FORK_GUARD in str(job.get("if", "")), (
            f"{path.name}:{job_id} lacks the same-repo guard"
        )


def test_required_contexts_map_to_exactly_one_job(workflows: dict[str, Any]) -> None:
    registry = json.loads((REPO / ".github" / "required-checks.json").read_text())["contexts"]
    rendered: dict[str, list[tuple[str, str]]] = {}
    for name, wf in workflows.items():
        for job_id, job in wf["jobs"].items():
            for ctx in _render_name(str(job.get("name", job_id)), job):
                rendered.setdefault(ctx, []).append((name, job_id))
    for entry in registry:
        hits = rendered.get(entry["context"], [])
        assert hits == [(entry["workflow"], entry["job"])], f"{entry['context']!r} -> {hits}"
        wf = workflows[entry["workflow"]]
        for trigger, spec in _triggers(wf).items():
            assert not (isinstance(spec, dict) and ("paths" in spec or "paths-ignore" in spec)), (
                f"required workflow {entry['workflow']} has a workflow-level path filter on {trigger}"
            )
        if not entry["pr_only"]:
            assert "push" in _triggers(wf), f"{entry['workflow']} must also run on push"


def test_commitlint_has_no_exemptions() -> None:
    assert "ignores:" not in (WORKFLOWS / "commit-lint.yml").read_text()


def test_vv_scale_resolving_has_no_schedule(workflows: dict[str, Any]) -> None:
    assert "schedule" not in _triggers(workflows["vv-scale-resolving.yml"])


def test_docs_sync_keeps_full_history(workflows: dict[str, Any]) -> None:
    steps = workflows["docs-sync.yml"]["jobs"]["status-block"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0


def test_dependabot_prefix_names_the_current_stage() -> None:
    stage = (REPO / ".aero-stage").read_text().strip()
    config = yaml.safe_load((REPO / ".github" / "dependabot.yml").read_text())
    prefixes = {u["commit-message"]["prefix"] for u in config["updates"]}
    assert prefixes == {f"ci(stage-{stage})"}, prefixes


# --- Stage 22 (ADR-051): no V&V workflow is green when it measured nothing ------------------

VV_WORKFLOWS = (
    "vv-smoke.yml",
    "vv-transonic.yml",
    "vv-required.yml",
    "moving-vv.yml",
    "vv-scale-resolving.yml",
)
# The jobs that run the cluster V&V suite through pytest (moving-vv uses a driver script).
_PYTEST_VV_JOBS = (
    ("vv-smoke.yml", "vv-smoke"),
    ("vv-transonic.yml", "vv-transonic"),
    ("vv-required.yml", "vv-required"),
)


def _runs(wf: dict[str, Any]) -> list[str]:
    return [
        str(step.get("run", ""))
        for job in wf.get("jobs", {}).values()
        for step in job.get("steps", [])
        if step.get("run")
    ]


def test_every_dvc_pull_is_targeted_and_fails_loudly(workflows: dict[str, Any]) -> None:
    """`dvc pull --quiet || echo "dvc pull skipped"` relabelled every failure as a skip."""
    pulls = [
        (name, line.strip())
        for name, wf in workflows.items()
        for run in _runs(wf)
        for line in run.splitlines()
        if "dvc pull" in line and not line.strip().startswith("#")
    ]
    for name, line in pulls:
        assert "||" not in line, f"{name}: a dvc pull must fail loudly: {line}"
        assert "--quiet" not in line and " -q" not in line, f"{name}: never quiet: {line}"
        assert re.search(r"\S+\.dvc\b", line), f"{name}: a dvc pull must name its target: {line}"


def test_vv_transonic_has_no_schedule(workflows: dict[str, Any]) -> None:
    """Dispatch only (operator decision 2026-10-16): the frozen SU2 stack is not a nightly signal."""
    assert set(_triggers(workflows["vv-transonic.yml"])) == {"workflow_dispatch"}


@pytest.mark.parametrize("name", VV_WORKFLOWS)
def test_every_vv_workflow_writes_a_step_summary(name: str, workflows: dict[str, Any]) -> None:
    assert any("GITHUB_STEP_SUMMARY" in run for run in _runs(workflows[name])), name


@pytest.mark.parametrize("name", VV_WORKFLOWS)
def test_no_vv_workflow_relabels_a_failure_with_echo(name: str, workflows: dict[str, Any]) -> None:
    for run in _runs(workflows[name]):
        assert "|| echo" not in run, f"{name}: `|| echo` turns a failure into a green step"


@pytest.mark.parametrize(("name", "job"), _PYTEST_VV_JOBS)
def test_pytest_vv_jobs_require_the_cluster_and_record_the_deselection(
    name: str, job: str, workflows: dict[str, Any]
) -> None:
    env = workflows[name]["jobs"][job].get("env", {})
    assert env.get("AERO_VV_REQUIRE_CLUSTER") == "1", name
    assert env.get("AERO_VV_DESELECTED_JSON"), name
    assert any("--junitxml=" in run for run in _runs(workflows[name])), name


def test_active_stack_selections_exclude_the_frozen_stack_and_documented_no_gos(
    workflows: dict[str, Any],
) -> None:
    required = workflows["vv-required.yml"]["jobs"]["vv-required"]["env"]["VV_SELECTION"]
    smoke = "\n".join(_runs(workflows["vv-smoke.yml"]))
    for text in (required, smoke):
        assert "not su2" in text and "not unmeasurable" in text and "not moving" in text
    transonic = workflows["vv-transonic.yml"]["jobs"]["vv-transonic"]["env"]["VV_SELECTION"]
    assert transonic.startswith("su2 and ")
