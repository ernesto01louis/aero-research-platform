"""Reader for preCICE's ``TXTTableWriter`` output (watch-points, iteration logs).

Both the watch-point files and ``precice-<Participant>-iterations.log`` are written by
the same C++ helper, whose format has two quirks that matter when a file is read while
the run is still going:

* the header line is emitted with a **leading two-space delimiter** and carries no
  comment marker, so it must be recognised by position (first non-empty line), not by
  a ``#`` prefix;
* each data row is prefixed — not terminated — by ``"\\n"``. The file therefore has no
  trailing newline, and the final row of a *live* file can be a partial write.

A partial trailing row is dropped and counted (:attr:`TxtTable.n_dropped`); a malformed
row anywhere else is a hard error, because that is data corruption rather than the
expected consequence of reading a file that is still being appended to.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=False,
    validate_assignment=True,
    validate_default=True,
)


class TxtTableError(RuntimeError):
    """A preCICE TXT table could not be read."""


class TxtTable(BaseModel):
    """A parsed TXT table: named columns and their rows, as strings."""

    model_config = _STRICT

    path: Path
    columns: tuple[str, ...] = Field(..., min_length=1)
    rows: tuple[tuple[str, ...], ...] = ()
    n_dropped: int = Field(
        default=0,
        ge=0,
        le=1,
        description="1 if a partially-written trailing row was dropped (live file).",
    )

    @model_validator(mode="after")
    def _rectangular(self) -> TxtTable:
        width = len(self.columns)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"{self.path}: row {index} has {len(row)} fields, expected {width}"
                )
        return self

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    def column(self, name: str) -> tuple[str, ...]:
        try:
            index = self.columns.index(name)
        except ValueError:
            raise TxtTableError(
                f"{self.path}: no column {name!r} (have: {', '.join(self.columns)})"
            ) from None
        return tuple(row[index] for row in self.rows)

    def floats(self, name: str) -> tuple[float, ...]:
        try:
            return tuple(float(v) for v in self.column(name))
        except ValueError as exc:
            raise TxtTableError(f"{self.path}: column {name!r} is not numeric — {exc}") from exc

    def ints(self, name: str) -> tuple[int, ...]:
        try:
            return tuple(int(v) for v in self.column(name))
        except ValueError as exc:
            raise TxtTableError(f"{self.path}: column {name!r} is not integral — {exc}") from exc


def read_txt_table(path: Path, *, expected_columns: tuple[str, ...] | None = None) -> TxtTable:
    """Parse a preCICE TXT table.

    `expected_columns`, when given, must match the file's header EXACTLY. Callers derive
    it from the configuration (see
    :meth:`aero.adapters.precice.config.PreciceConfig.watchpoint_columns`) so that an
    upstream reordering or an added data field is a loud failure rather than a silently
    transposed signal.
    """
    if not path.is_file():
        raise TxtTableError(f"{path}: no such file — did the participant write it?")
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        raise TxtTableError(f"{path}: empty — the participant produced no output")

    columns = tuple(non_empty[0].split())
    if not columns:
        raise TxtTableError(f"{path}: unreadable header line")
    if expected_columns is not None and columns != expected_columns:
        raise TxtTableError(
            f"{path}: header {columns} does not match the header predicted from the "
            f"preCICE configuration {expected_columns}. Refusing to index columns by "
            "position — the upstream data layout has changed."
        )

    width = len(columns)
    body = non_empty[1:]
    rows: list[tuple[str, ...]] = []
    n_dropped = 0
    for index, line in enumerate(body):
        fields = tuple(line.split())
        if len(fields) == width:
            rows.append(fields)
            continue
        is_last = index == len(body) - 1
        if is_last and len(fields) < width:
            # Expected while the solve is running: the row is mid-write.
            n_dropped = 1
            continue
        raise TxtTableError(
            f"{path}: row {index} has {len(fields)} fields, expected {width} — "
            "this is corruption, not a partial write (only the final row may be partial)"
        )

    return TxtTable(path=path, columns=columns, rows=tuple(rows), n_dropped=n_dropped)
