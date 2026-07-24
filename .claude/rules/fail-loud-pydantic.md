# Rule — Fail-Loud Pydantic

## Scope

Loaded lazily when editing any pydantic model in `aero/`. Constitution
Invariant 2 in operational form.

## The contract

Every pydantic model in `aero/` must:

```python
from pydantic import BaseModel, ConfigDict, Field


class CaseSpec(BaseModel):
    model_config = ConfigDict(
        extra="forbid",  # unknown keys raise ValidationError
        frozen=True,  # immutable after construction (where reasonable)
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )

    name: str = Field(..., min_length=1, description="Case name")
    reynolds: float = Field(..., gt=0, description="Reynolds number")
    # ...
```

## What NOT to do

- **Do not** use `extra="allow"` or `extra="ignore"`. Unknown keys
  always mean drift — fail at validation time.
- **Do not** catch `pydantic.ValidationError` and substitute a default;
  let it propagate up to the CLI boundary where a friendly error string
  is rendered.
- **Do not** silently coerce types via custom validators that "guess
  what the user meant". If the user supplied `reynolds: "5e6"` as a
  string and the field is `float`, pydantic 2 does that coercion by
  default — that's fine. But don't write a validator that turns
  `reynolds: "ten thousand"` into `10000.0`.
- **Do not** add `Optional[...]` to a field just to make a default
  optional — make the default explicit and required where it matters.

## The Hydra-pydantic boundary

Hydra resolves layered configs into a plain dict. The boundary into the
typed world is exactly one place per CLI command:

```python
from omegaconf import OmegaConf
from pydantic import ValidationError


@app.command()
def run(case_name: str) -> None:
    raw_cfg = hydra.compose(config_name=case_name)
    plain_dict = OmegaConf.to_container(raw_cfg, resolve=True)
    try:
        case = CaseSpec.model_validate(plain_dict)
    except ValidationError as exc:
        # User-facing CLI boundary: render friendly, exit nonzero
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=2)
    # ... everything from here on is typed
    solver.prepare(case)
```

## Provenance hook

When serializing a resolved config for the four-tuple's `config_hash`:

```python
import json, hashlib
from omegaconf import OmegaConf


def config_hash(cfg) -> str:
    plain = OmegaConf.to_container(cfg, resolve=True)
    canonical = json.dumps(plain, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
```

This is what gets logged as the MLflow `config_hash` tag.

## Why fail-loud

Silent fallbacks become silent corruption. In a provenance-mandated
project, a config field that drifts and goes uncaught means the
four-tuple no longer maps a run back to the inputs that produced it.
The cost of a strict failure ("error: unknown field 'reynold' — did
you mean 'reynolds'?") is one line of feedback. The cost of a silent
fallback is a misattributed publication.
