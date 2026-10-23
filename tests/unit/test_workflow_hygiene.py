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
import os
import re
import subprocess
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


# --- Stage 23: moving-vv's dispatch input is validated as one string (ADR-049 H-09) ----------
#
# The Stage-21 guard piped `printf '%s' "$CASE_INPUT"` into `grep -Eq`: grep saw zero lines on
# the empty input of every scheduled run, so from 2026-10-18 the job exited 2 in 14 s having
# measured nothing, and `grep -q` accepted a multi-line input as soon as any one line matched
# (`$'\n-h'` reached the driver as `-h`, which printed help and recorded "-h: PASS").

_VALIDATE = "Validate the dispatch input"
_RUN_CASES = "Run the moving-mesh cases through the Stage-11 driver"
_DEFAULT_CASES = "oscillating_cylinder_lockin plunging_airfoil_hg2007"


def _moving_vv_step(workflows: dict[str, Any], name: str) -> dict[str, Any]:
    steps = workflows["moving-vv.yml"]["jobs"]["moving-vv"]["steps"]
    matches = [s for s in steps if s.get("name") == name]
    assert len(matches) == 1, f"moving-vv has {len(matches)} steps named {name!r}"
    return matches[0]


def _run_step(script: str, env: dict[str, str], cwd: Path) -> tuple[int, str, str]:
    """Run a step's script the way GitHub does (`bash -e`, no pipefail) in a scratch directory."""
    summary, github_env = cwd / "summary.md", cwd / "github_env"
    summary.write_text("")
    github_env.write_text("")
    proc = subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=cwd,
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_ENV": str(github_env),
            **env,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return proc.returncode, summary.read_text(), github_env.read_text()


@pytest.mark.parametrize(
    ("case_input", "expected"),
    [
        ("", _DEFAULT_CASES),
        (" ", _DEFAULT_CASES),
        ("   ", _DEFAULT_CASES),
        ("oscillating_cylinder_lockin", "oscillating_cylinder_lockin"),
        (
            " plunging_airfoil_hg2007_st03  oscillating_cylinder_lockin ",
            "plunging_airfoil_hg2007_st03 oscillating_cylinder_lockin",
        ),
    ],
)
def test_moving_vv_accepts_a_blank_or_valid_case_input(
    case_input: str, expected: str, workflows: dict[str, Any], tmp_path: Path
) -> None:
    """A scheduled run (empty input) and a blank dispatch run the defaults, never zero cases."""
    script = _moving_vv_step(workflows, _VALIDATE)["run"]
    rc, summary, github_env = _run_step(script, {"CASE_INPUT": case_input}, tmp_path)
    assert rc == 0, (case_input, summary)
    assert github_env == f"MOVING_VV_CASES={expected}\n"


@pytest.mark.parametrize(
    "case_input",
    ["a;b", "x;id", "$(id)", "`id`", "-h", "\n-h", "ok\n;evil", "ok\n", "Oscillating", "a\tb"],
)
def test_moving_vv_refuses_anything_but_one_line_of_case_keys(
    case_input: str, workflows: dict[str, Any], tmp_path: Path
) -> None:
    script = _moving_vv_step(workflows, _VALIDATE)["run"]
    rc, summary, github_env = _run_step(script, {"CASE_INPUT": case_input}, tmp_path)
    assert rc == 2, repr(case_input)
    assert github_env == "", "a refused input must not reach the run step"
    assert "refused" in summary, "the step summary must say nothing was measured"


def test_moving_vv_fails_rather_than_run_zero_cases(
    workflows: dict[str, Any], tmp_path: Path
) -> None:
    script = _moving_vv_step(workflows, _RUN_CASES)["run"]
    driver_calls = tmp_path / "driver_calls"
    shim = tmp_path / ".venv" / "bin" / "python"
    shim.parent.mkdir(parents=True)
    shim.write_text(f'#!/bin/sh\necho "$@" >> {driver_calls}\n')
    shim.chmod(0o755)
    rc, summary, _ = _run_step(script, {"MOVING_VV_CASES": "", "AERO_SOLVE_HOST": "x"}, tmp_path)
    assert rc == 1
    assert "nothing to run" in summary
    assert not driver_calls.exists(), "the driver must not run when no case is named"


def test_moving_vv_default_cases_are_registered_unsteady_cases(workflows: dict[str, Any]) -> None:
    from aero.vv.unsteady import UNSTEADY_CASES

    script = _moving_vv_step(workflows, _VALIDATE)["run"]
    defaults = re.search(r"words=\(([a-z0-9_ ]+)\)", script)
    assert defaults is not None, "the validation step must name its default cases"
    assert defaults.group(1).split() == _DEFAULT_CASES.split()
    assert set(_DEFAULT_CASES.split()) <= set(UNSTEADY_CASES)


def test_only_the_secretless_validation_step_reads_the_moving_vv_input(
    workflows: dict[str, Any],
) -> None:
    steps = workflows["moving-vv.yml"]["jobs"]["moving-vv"]["steps"]
    readers = [s.get("name") for s in steps if "github.event.inputs" in json.dumps(s)]
    assert readers == [_VALIDATE]
    assert "secrets." not in json.dumps(_moving_vv_step(workflows, _VALIDATE))


# --- Stage 23: the V&V jobs install the lock; one dated pip-audit waiver ----------------------
#
# The self-hosted V&V jobs used `uv pip install -e`, which re-resolves and ignores uv.lock (the
# 2026-10-16 FULL run used mlflow 3.17.1 against 3.12.0 locked), so a green V&V run said nothing
# about the lock the release ships. ADR-049 H-15 now covers them (operator decision 2026-10-21).


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_self_hosted_jobs_install_exactly_the_lock(path: Path, workflows: dict[str, Any]) -> None:
    for job_name, job in workflows[path.name].get("jobs", {}).items():
        if not _self_hosted(job):
            continue
        for step in job.get("steps", []):
            run = step.get("run", "")
            assert "uv pip install" not in run, f"{path.name}:{job_name}: unlocked install"
            assert "uv venv" not in run, f"{path.name}:{job_name}: unlocked environment"


def test_a_lock_change_triggers_the_full_vv_required_run(workflows: dict[str, Any]) -> None:
    steps = workflows["vv-required.yml"]["jobs"]["vv-required"]["steps"]
    (filter_step,) = [s for s in steps if s.get("id") == "filter"]
    relevant = yaml.safe_load(filter_step["with"]["filters"])["relevant"]
    assert "uv.lock" in relevant and "pyproject.toml" in relevant


def test_pip_audit_waives_exactly_one_advisory_until_its_review_date(
    workflows: dict[str, Any],
) -> None:
    import datetime as dt

    steps = workflows["dependency-licences.yml"]["jobs"]["audit"]["steps"]
    (audit,) = [s for s in steps if "pip-audit" in s.get("run", "")]
    assert re.findall(r"--ignore-vuln\s+(\S+)", audit["run"]) == ["PYSEC-2026-2447"]
    review_by = dt.date.fromisoformat(audit["env"]["PIP_AUDIT_WAIVER_REVIEW_BY"])
    assert dt.datetime.now(dt.UTC).date() <= review_by, (
        "the diskcache waiver (PYSEC-2026-2447) is past its review date: re-check whether a "
        "fixed release exists, then renew the waiver with a new date or drop it"
    )


# --- Stage 23: the MinIO keys only where DVC pulls (least privilege) --------------------------

_DVC_KEY = re.compile(r"secrets\.AERO_DVC_|AWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY)")


def test_the_dvc_keys_reach_only_a_step_that_pulls() -> None:
    """Since O-07 (ADR-052) no provenance term reads the DVC remote, so the keys are exposed only
    to a step whose own `run` is a `dvc pull`: today, vv-transonic's targeted ONERA M6 mesh pull.
    A workflow- or job-level `env` would hand them to every step, so they may not appear there."""
    holders = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        wf = _load(path)
        assert not _DVC_KEY.search(yaml.safe_dump(wf.get("env") or {})), (
            f"{path.name}: top-level env"
        )
        for job_name, job in (wf.get("jobs") or {}).items():
            assert not _DVC_KEY.search(yaml.safe_dump(job.get("env") or {})), (
                f"{path.name}:{job_name}: job-level env"
            )
            for step in job.get("steps") or []:
                if _DVC_KEY.search(yaml.safe_dump(step.get("env") or {})):
                    holders.append((path.name, step.get("name")))
                    assert "dvc pull" in (step.get("run") or ""), (
                        f"{path.name}:{step.get('name')}: holds the DVC keys but does not pull"
                    )
    assert holders == [("vv-transonic.yml", "Fetch the ONERA M6 mesh (DVC, fail-loud)")]
