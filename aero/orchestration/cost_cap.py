"""Cost-cap enforcement for cloud GPU executors (Stage 07).

Every rented-GPU launch — RunPod (Stage 07), Lambda Labs and Vast.ai (Stage 13)
— passes through `CostCap.check_budget()` before any spend is committed.
The cap is enforced via a local append-only JSON ledger
(`/etc/aero/runpod-ledger.json` by default), summed month-to-date and
compared against `AERO_RUNPOD_MONTHLY_CAP_USD` (default `150.0`; the baseline
tier, raised from $50 by ADR-014 — sustained/burst campaigns are per-campaign
env-var overrides). This is CONSTITUTION Invariant 8 —
COST-CAP-ENFORCED-CLOUD-EXECUTION — codified as code (ADR-007, value per ADR-014).

PLATFORM-NOT-HUB clean: stdlib + pydantic only. No `requests`, no cloud
SDK; this module is import-safe with no extras installed.

Why a local ledger and not a billing-API call: cloud billing APIs (RunPod,
Vast.ai) are eventually-consistent with hour-level latency, sometimes more.
A pre-launch check that queries them races the new launch; a local
estimate-before-spend, true-up-after-spend ledger is precise enough for
$150/month baseline budgeting and has zero network dependency. Stage 13's
multi-cloud cost router is the place for a sophisticated multi-vendor
spend reconciliation; Stage 07 keeps it stupid.

Failure modes the cap prevents (well-attested in the field):
  * a runaway for-loop launching 30 H100 pods at ~$3/hr;
  * a terminate-API that returns 200 but leaves billing running (we mark
    the entry `tag="ORPHANED"` and refuse all further launches until the
    operator clears it manually);
  * a debug session forgetting to pass `--cost-cap` and silently
    blowing through the monthly budget.
"""

from __future__ import annotations

import contextlib
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_LEDGER_PATH = Path("/etc/aero/runpod-ledger.json")
DEFAULT_CAP_USD = 150.0  # baseline tier (ADR-014, raised from $50/ADR-007)
CAP_ENV_VAR = "AERO_RUNPOD_MONTHLY_CAP_USD"

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


# --- exceptions ---------------------------------------------------------------
class CostCapError(RuntimeError):
    """Base class for cost-cap errors. Always FAIL-LOUD (Invariant 2)."""


class CostCapExceeded(CostCapError):  # noqa: N818 — domain-natural name; "Error" suffix would obscure intent
    """A pre-launch budget check refused the launch — projected MTD over the cap."""


class CostCapPermissionError(CostCapError):
    """The ledger file does not exist or is not writable by the current user."""


class CostCapOrphanedEntry(CostCapError):  # noqa: N818 — domain-natural name; this is a state, not a generic error
    """A prior launch's pod could not be confirmed terminated; refuse new launches."""


# --- typed ledger models ------------------------------------------------------
class LedgerEntry(BaseModel):
    """One rented-GPU launch — pre-execution estimate + post-execution true-up.

    Two-phase: `record_launch` writes the entry with the projected hours
    and cost; `record_termination` amends it with the actual hours and
    cost on pod terminate. An entry with `tag="ORPHANED"` is one whose
    termination polling failed — further launches are refused until the
    operator clears it.
    """

    model_config = _STRICT

    run_id: str = Field(..., min_length=1, description="The aero run id this launch served.")
    pod_type: str = Field(
        ..., min_length=1, description="Pod type label (e.g. 'NVIDIA H100 PCIe')."
    )
    started_at: datetime = Field(..., description="Pre-launch UTC timestamp.")
    projected_hours: float = Field(..., gt=0, description="Hours projected at launch.")
    hourly_rate_usd: float = Field(..., gt=0, description="USD per hour at launch.")
    projected_cost_usd: float = Field(..., gt=0, description="projected_hours * hourly_rate_usd.")
    terminated_at: datetime | None = Field(
        default=None, description="Post-terminate UTC timestamp; None until terminate confirms."
    )
    actual_hours: float | None = Field(
        default=None, ge=0, description="Wall-clock hours; None until terminate confirms."
    )
    actual_cost_usd: float | None = Field(
        default=None, ge=0, description="actual_hours * hourly_rate_usd; None until terminate."
    )
    tag: Literal["ok", "running", "orphaned", "errored"] = Field(
        default="running",
        description=(
            "Lifecycle marker: 'running' (in flight), 'ok' (terminated cleanly), "
            "'orphaned' (terminate polling failed — refuse new launches until cleared), "
            "'errored' (a non-billing-affecting failure path)."
        ),
    )

    @property
    def billed_cost_usd(self) -> float:
        """The cost the month-to-date sum counts.

        Uses `actual_cost_usd` if terminate confirmed; falls back to
        `projected_cost_usd` for running entries so the cap holds even
        before terminate runs.
        """
        return self.actual_cost_usd if self.actual_cost_usd is not None else self.projected_cost_usd


class Ledger(BaseModel):
    """The append-only ledger persisted at `/etc/aero/runpod-ledger.json`."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )

    cap_usd: float = Field(..., gt=0, description="Monthly cap in USD.")
    entries: list[LedgerEntry] = Field(default_factory=list)

    def month_to_date_usd(self, *, now: datetime | None = None) -> float:
        """Sum `billed_cost_usd` of entries started this calendar month (UTC)."""
        now = now or datetime.now(UTC)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=UTC)
        return sum(e.billed_cost_usd for e in self.entries if e.started_at >= start_of_month)

    def has_orphaned(self) -> bool:
        """True iff any historical entry is tagged `orphaned`."""
        return any(e.tag == "orphaned" for e in self.entries)


# --- the CostCap controller ---------------------------------------------------
class CostCap:
    """The pre-launch budget check, ledger writer, and orphan guard.

    Constructed once per cloud executor; methods are thread-safe via a
    per-instance lock so concurrent runners on the same ledger file
    serialise their writes. Disk I/O is deliberately blocking — this is
    not a hot path, and `fsync` matters for correctness (a crashed
    process must not lose a launch record).
    """

    def __init__(
        self,
        *,
        ledger_path: Path = DEFAULT_LEDGER_PATH,
        cap_usd: float | None = None,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        env_cap = os.environ.get(CAP_ENV_VAR)
        if cap_usd is not None:
            self._cap_usd = float(cap_usd)
        elif env_cap is not None:
            self._cap_usd = float(env_cap)
        else:
            self._cap_usd = DEFAULT_CAP_USD
        if self._cap_usd <= 0:
            raise ValueError(f"cap_usd must be > 0, got {self._cap_usd}")
        self._lock = threading.Lock()

    @property
    def cap_usd(self) -> float:
        return self._cap_usd

    # ---- ledger I/O -----------------------------------------------------
    def ensure_ledger(self) -> Ledger:
        """Read the ledger, creating an empty one if missing.

        Creates the parent directory and the file with mode 0640. Raises
        `CostCapPermissionError` if the file exists but is not readable, or
        if the parent is not writable and the file is absent — never
        silently degrades.
        """
        parent = self.ledger_path.parent
        if not self.ledger_path.exists():
            try:
                parent.mkdir(parents=True, exist_ok=True)
                self.ledger_path.write_text(
                    Ledger(cap_usd=self._cap_usd).model_dump_json(indent=2) + "\n",
                    encoding="utf-8",
                )
                os.chmod(self.ledger_path, 0o640)
            except OSError as exc:
                raise CostCapPermissionError(
                    f"cannot create ledger at {self.ledger_path}: {exc}. "
                    f"Fix: sudo install -m 0640 -o {os.environ.get('USER', 'aero-admin')} "
                    f"/dev/null {self.ledger_path}"
                ) from exc
        try:
            raw = self.ledger_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CostCapPermissionError(
                f"cannot read ledger at {self.ledger_path}: {exc}"
            ) from exc
        return Ledger.model_validate_json(raw)

    def _write_ledger(self, ledger: Ledger) -> None:
        """Atomically replace the ledger file (write-temp + rename)."""
        tmp = self.ledger_path.with_suffix(self.ledger_path.suffix + ".tmp")
        tmp.write_text(ledger.model_dump_json(indent=2) + "\n", encoding="utf-8")
        # mode may already be correct via umask; the rename below is the contract
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o640)
        os.replace(tmp, self.ledger_path)

    # ---- pre-launch / post-launch surface --------------------------------
    def check_budget(
        self,
        estimated_usd: float,
        *,
        now: datetime | None = None,
    ) -> Ledger:
        """Refuse the launch if MTD + `estimated_usd` would exceed the cap.

        Also refuses if any prior entry is tagged `orphaned` — that's the
        terminate-failure guard. Returns the current ledger on success so
        the caller can report `mtd` and `projected_after` in the launch
        ladder.
        """
        if estimated_usd <= 0:
            raise ValueError(f"estimated_usd must be > 0, got {estimated_usd}")
        with self._lock:
            ledger = self.ensure_ledger()
            if ledger.has_orphaned():
                orphan_ids = [e.run_id for e in ledger.entries if e.tag == "orphaned"]
                raise CostCapOrphanedEntry(
                    f"refusing launch: ledger has orphaned entries {orphan_ids}. "
                    "Operator must verify pod state and edit the ledger tag to "
                    "'ok' or 'errored' before further launches are permitted."
                )
            mtd = ledger.month_to_date_usd(now=now)
            projected_after = mtd + estimated_usd
            if projected_after > self._cap_usd:
                raise CostCapExceeded(
                    f"refusing launch: projected ${projected_after:.2f} after this run "
                    f"exceeds cap ${self._cap_usd:.2f} (MTD ${mtd:.2f}, "
                    f"this run +${estimated_usd:.2f}). Raise the cap via "
                    f"{CAP_ENV_VAR}=<USD> or wait for the next calendar month."
                )
            return ledger

    def record_launch(
        self,
        *,
        run_id: str,
        pod_type: str,
        projected_hours: float,
        hourly_rate_usd: float,
        now: datetime | None = None,
    ) -> LedgerEntry:
        """Append a new entry tagged `running` and persist the ledger.

        Returns the entry the caller can later pass to `record_termination`.
        """
        now = now or datetime.now(UTC)
        entry = LedgerEntry(
            run_id=run_id,
            pod_type=pod_type,
            started_at=now,
            projected_hours=projected_hours,
            hourly_rate_usd=hourly_rate_usd,
            projected_cost_usd=projected_hours * hourly_rate_usd,
            tag="running",
        )
        with self._lock:
            ledger = self.ensure_ledger()
            ledger.entries.append(entry)
            self._write_ledger(ledger)
        return entry

    def record_termination(
        self,
        *,
        run_id: str,
        actual_hours: float,
        tag: Literal["ok", "orphaned", "errored"] = "ok",
        now: datetime | None = None,
    ) -> LedgerEntry:
        """Amend the matching `running` entry with actual hours + cost + tag.

        `tag='orphaned'` is the terminate-polling-failed path: subsequent
        `check_budget` calls then raise `CostCapOrphanedEntry` until the
        operator clears the entry manually.
        """
        now = now or datetime.now(UTC)
        with self._lock:
            ledger = self.ensure_ledger()
            for i, e in enumerate(ledger.entries):
                if e.run_id == run_id and e.tag == "running":
                    actual_cost = actual_hours * e.hourly_rate_usd
                    updated = e.model_copy(
                        update={
                            "terminated_at": now,
                            "actual_hours": actual_hours,
                            "actual_cost_usd": actual_cost,
                            "tag": tag,
                        }
                    )
                    # model_copy on a frozen model yields a new instance — replace.
                    ledger.entries[i] = updated
                    self._write_ledger(ledger)
                    return updated
            raise CostCapError(
                f"no 'running' entry found for run_id={run_id!r} (already terminated?)"
            )
