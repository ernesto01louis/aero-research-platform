"""FAIL-LOUD, structurally: every pydantic model in ``aero/`` forbids unknown keys.

CONSTITUTION Invariant 2 / Hard Rule 2 require ``extra='forbid'`` on every model. At Stage 21
open all 178 models complied, but nothing enforced it (ADR-049 H-13): tests checked a handful of
models individually, and a new model without ``model_config`` would silently default to
pydantic's ``extra='ignore'``, dropping unknown keys instead of failing.

Two passes:

* AST: every ``ConfigDict(...)`` call under ``aero/`` passes the literal ``extra="forbid"``. This
  covers modules that cannot be imported in this environment.
* Runtime: every ``BaseModel`` subclass defined in an importable ``aero`` module has
  ``model_config["extra"] == "forbid"``, inherited or direct. A floor on the number of models
  seen keeps the pass from going vacuous if imports start failing.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import aero
import pytest
from pydantic import BaseModel

pytestmark = pytest.mark.stage_21

AERO = Path(aero.__file__).resolve().parent
_MIN_MODELS = 170  # 178 at Stage 21 open; the floor stops a silently shrinking scan


def test_every_configdict_call_forbids_extra_keys() -> None:
    offenders: list[str] = []
    calls = 0
    for path in sorted(AERO.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "ConfigDict":
                continue
            calls += 1
            extra = {kw.arg: kw.value for kw in node.keywords}.get("extra")
            if not (isinstance(extra, ast.Constant) and extra.value == "forbid"):
                offenders.append(f"{path.relative_to(AERO.parent)}:{node.lineno}")
    assert calls >= 80
    assert not offenders, f"ConfigDict without extra='forbid': {offenders}"


def test_every_importable_model_forbids_extra_keys() -> None:
    models: dict[str, type[BaseModel]] = {}
    for info in pkgutil.walk_packages(aero.__path__, "aero."):
        if info.name.endswith("__main__"):
            continue
        try:
            module = importlib.import_module(info.name)
        except ModuleNotFoundError as exc:
            # Only an absent OPTIONAL third-party dependency excuses a module; a missing aero
            # module is a real failure.
            assert exc.name is not None and not exc.name.startswith("aero"), exc
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseModel) and obj.__module__.startswith("aero."):
                models[f"{obj.__module__}.{obj.__qualname__}"] = obj
    assert len(models) >= _MIN_MODELS, f"only {len(models)} models seen"
    lax = sorted(n for n, cls in models.items() if cls.model_config.get("extra") != "forbid")
    assert not lax, f"models that do not forbid extra keys: {lax}"
