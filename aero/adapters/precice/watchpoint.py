"""Reader for preCICE watch-point output (`precice-<Participant>-watchpoint-<name>.log`).

A watch-point is preCICE's own probe: it records one row per *completed* time window
with the tracked point's coordinate and every data field carried by its mesh. For
Turek-Hron FSI3 the Solid participant watches ``Flap-Tip`` at the flag tip's undeformed
position (0.6, 0.2) — benchmark point A — so `Displacement1` is the transverse tip
deflection the gate is stated on.

The reader converts a watch-point into :class:`aero.postprocess.Signal`, which is the
unit the platform's unsteady toolkit (`dominant_frequency`, `segment_cycles`,
`detect_cycle_convergence`) already consumes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.adapters.precice._txt_table import TxtTableError, read_txt_table
from aero.postprocess import Signal

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class WatchpointError(RuntimeError):
    """A preCICE watch-point file could not be read or is not usable."""


class WatchpointTrace(BaseModel):
    """A parsed watch-point: the time column plus every data column, by name."""

    model_config = _STRICT

    path: Path
    participant: str = Field(..., min_length=1)
    watch_point: str = Field(..., min_length=1)
    columns: tuple[str, ...] = Field(..., min_length=2)
    t: tuple[float, ...] = Field(..., min_length=1)
    values: dict[str, tuple[float, ...]] = Field(..., min_length=1)
    n_dropped: int = Field(default=0, ge=0, description="Partial trailing rows dropped.")

    @model_validator(mode="after")
    def _consistent(self) -> WatchpointTrace:
        n = len(self.t)
        for name, series in self.values.items():
            if len(series) != n:
                raise ValueError(
                    f"{self.path}: column {name!r} has {len(series)} samples but Time has {n}"
                )
        if n > 1:
            t = np.asarray(self.t, dtype=np.float64)
            if not np.all(np.diff(t) > 0.0):
                raise ValueError(
                    f"{self.path}: the Time column is not strictly increasing. preCICE writes "
                    "one row per COMPLETED time window, so this means the run was restarted "
                    "into an existing log or the file interleaves two runs — the record is "
                    "ambiguous and is not analysable."
                )
        return self

    @property
    def n_rows(self) -> int:
        return len(self.t)

    @property
    def t_end(self) -> float:
        return self.t[-1]

    def signal(self, column: str) -> Signal:
        """The named column as a :class:`Signal`."""
        if column not in self.values:
            raise WatchpointError(
                f"{self.path}: no data column {column!r} (have: {', '.join(sorted(self.values))})"
            )
        return Signal.from_arrays(
            np.asarray(self.t, dtype=np.float64),
            np.asarray(self.values[column], dtype=np.float64),
            name=column,
        )

    def truncate(self, *, t_max: float) -> WatchpointTrace:
        """A copy keeping only samples with ``t <= t_max`` (fail-loud if that is empty)."""
        keep = [index for index, time in enumerate(self.t) if time <= t_max]
        if not keep:
            raise WatchpointError(
                f"{self.path}: truncating at t <= {t_max:g} leaves no samples "
                f"(record starts at t = {self.t[0]:g})"
            )
        return self.model_copy(
            update={
                "t": tuple(self.t[i] for i in keep),
                "values": {
                    name: tuple(series[i] for i in keep) for name, series in self.values.items()
                },
            }
        )


def watchpoint_path(case_root: Path, participant_dir: str, participant: str, name: str) -> Path:
    """Where preCICE writes a watch-point: in the participant's working directory."""
    return case_root / participant_dir / f"precice-{participant}-watchpoint-{name}.log"


def read_watchpoint(
    path: Path,
    *,
    participant: str,
    watch_point: str,
    expected_columns: tuple[str, ...] | None = None,
) -> WatchpointTrace:
    """Read a watch-point file into a :class:`WatchpointTrace`.

    `expected_columns` should come from
    :meth:`aero.adapters.precice.config.PreciceConfig.watchpoint_columns` so the header
    is verified against the configuration rather than assumed (ADR-036 gate C4).
    """
    try:
        table = read_txt_table(path, expected_columns=expected_columns)
    except TxtTableError as exc:
        raise WatchpointError(str(exc)) from exc

    if table.columns[0] != "Time":
        raise WatchpointError(
            f"{path}: first column is {table.columns[0]!r}, expected 'Time' — "
            "this does not look like a preCICE watch-point file"
        )
    if table.n_rows == 0:
        raise WatchpointError(
            f"{path}: header only, no completed time windows. The coupling has not "
            "advanced past its first window."
        )

    return WatchpointTrace(
        path=path,
        participant=participant,
        watch_point=watch_point,
        columns=table.columns,
        t=table.floats("Time"),
        values={name: table.floats(name) for name in table.columns[1:]},
        n_dropped=table.n_dropped,
    )
