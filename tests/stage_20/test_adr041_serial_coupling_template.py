"""ADR-041 D-B: the serial-implicit template, and the two properties that protect history.

The D-A rung established that the unmitigated stack reproduces the period-2 instability
(w1487, after attempt 1's w1703). D-B tests whether the scheme is the mechanism: under
parallel-implicit both participants advance from the same window state, so a parity
oscillation can live in the solid's half-step where the coupling residual never sees it.

Two things here are not design choices and are tested as such:

* **The IQN-ILS primary-data set drops to `{Displacement}`, forced by preCICE**, which
  accelerates only data exchanged from the `second` to the `first` participant under
  serial coupling — and `Force` flows Fluid(first) → Solid(second). Verified against
  preCICE's own validator in the SIF, which rejects the counterfactual by name:
  *"only data exchanged from the second to the first participant can be used for
  acceleration ... Please remove this acceleration data tag or switch to a parallel
  implicit coupling scheme."*
* **A serial spec's `config_hash` moves and the default path's does not.** The scheme is
  a keyword selecting a committed template through `AuthoredSource.template`, never a new
  pydantic field: a field would serialize into every spec and move every digest, breaking
  `_reattach` on records that describe runs already on disk — including both uncollected
  N3 attempt-1 submissions, one of them the completed rigid arm.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.precice.case import spec_config_digest
from aero.adapters.precice.config import PreciceConfigError, parse_precice_config
from aero.adapters.precice.template import (
    COUPLING_TEMPLATES,
    HG2007_SERIAL_TEMPLATE,
    HG2007_TEMPLATE,
    PreciceConfigValues,
    hg2007_expectation,
    read_template,
    render_precice_config,
    scheme_for_template,
    template_for_scheme,
    template_sha256,
)
from aero.vv.fsi.hg2007_flexible_foil import LEGACY_COUPLING_SCHEME, hg2007_case_spec

pytestmark = pytest.mark.stage_20

_KNOBS = dict(
    arm="flexible",
    rung="mid",
    time_window_size=2e-05,
    max_time=0.16,
    wall_clock_ceiling_s=43200,
    numerics_label="adr040-candidate",
    mpi_ranks=4,
)


def _values() -> PreciceConfigValues:
    return PreciceConfigValues(
        support_radius=0.0045,
        nose_watch_point=(0.0, 0.0),
        te_watch_point=(0.09, 0.0),
        exchange_directory=".",
        time_window_size=2e-05,
        max_time=0.16,
    )


def test_the_serial_template_differs_by_exactly_the_two_declared_changes() -> None:
    """ADR-041's header declares two C1 moves; a third would need its own ADR.

    Compared on the rendered configurations rather than the template text, so the
    explanatory comment block in the serial file cannot hide a substantive change.
    """
    values = _values()
    parallel = parse_precice_config(
        render_precice_config(values, template=HG2007_TEMPLATE),
        source=Path("parallel.xml"),
        sha256="0" * 64,
    ).coupling_scheme
    serial = parse_precice_config(
        render_precice_config(values, template=HG2007_SERIAL_TEMPLATE),
        source=Path("serial.xml"),
        sha256="0" * 64,
    ).coupling_scheme

    # change 1: the scheme
    assert (parallel.kind, serial.kind) == ("parallel-implicit", "serial-implicit")
    # change 2: the acceleration primary data, forced by preCICE
    assert parallel.acceleration.data == (("Displacement", "Solid-Mesh"), ("Force", "Solid-Mesh"))
    assert serial.acceleration.data == (("Displacement", "Solid-Mesh"),)
    # ...and NOTHING else in C1 moves
    assert parallel.max_iterations == serial.max_iterations == 50
    assert parallel.acceleration.kind == serial.acceleration.kind == "IQN-ILS"
    assert parallel.acceleration.filter_type == serial.acceleration.filter_type == "QR2"
    assert parallel.acceleration.filter_limit == serial.acceleration.filter_limit == 1e-2
    assert parallel.acceleration.initial_relaxation == serial.acceleration.initial_relaxation == 0.5
    assert (
        parallel.acceleration.max_used_iterations == serial.acceleration.max_used_iterations == 100
    )
    assert (
        parallel.acceleration.time_windows_reused == serial.acceleration.time_windows_reused == 15
    )
    assert [(m.data, m.limit) for m in parallel.convergence_measures] == [
        (m.data, m.limit) for m in serial.convergence_measures
    ]


def test_the_expectation_follows_the_scheme_rather_than_being_a_second_copy() -> None:
    """ "The expectation describes the template" has to keep holding for both templates."""
    values = _values()
    assert hg2007_expectation(values).acceleration_data == (
        ("Displacement", "Solid-Mesh"),
        ("Force", "Solid-Mesh"),
    )
    assert hg2007_expectation(values, coupling_scheme="serial-implicit").acceleration_data == (
        ("Displacement", "Solid-Mesh"),
    )


def test_both_templates_are_digest_verified_on_every_read() -> None:
    for scheme, name in COUPLING_TEMPLATES.items():
        assert read_template(name)  # raises if the bytes moved under SHA256SUMS
        assert template_sha256(name)
        assert template_for_scheme(scheme) == name
        assert scheme_for_template(name) == scheme
    with pytest.raises(PreciceConfigError, match="no committed HG2007 template"):
        template_for_scheme("explicit")  # type: ignore[arg-type]


def test_the_default_spec_digest_does_not_move_and_the_serial_one_does() -> None:
    """The property both live N3 digest pins and every historical record depend on."""
    default = hg2007_case_spec(**_KNOBS)
    explicit = hg2007_case_spec(**_KNOBS, coupling_scheme=LEGACY_COUPLING_SCHEME)
    serial = hg2007_case_spec(**_KNOBS, coupling_scheme="serial-implicit")

    assert spec_config_digest(default) == spec_config_digest(explicit)
    assert spec_config_digest(serial) != spec_config_digest(default)
    assert serial.source.template == HG2007_SERIAL_TEMPLATE
    assert serial.source.template_sha256 == template_sha256(HG2007_SERIAL_TEMPLATE)
    # the scheme is a keyword, never a field: no spec model grew one
    assert "coupling_scheme" not in default.model_dump()
    assert "coupling_scheme" not in default.source.model_dump()


def test_a_record_without_the_key_rebuilds_as_parallel_implicit() -> None:
    """How `_reattach` reads a submission written before the knob existed.

    It supplies LEGACY_COUPLING_SCHEME explicitly rather than leaning on the builder's
    default, because that default moves if a mitigated stack is adopted — and the two
    uncollected N3 attempt-1 records describe runs that really were parallel-implicit.
    """
    legacy_knobs = dict(_KNOBS)  # exactly what a pre-ADR-041 record carries
    rebuilt = hg2007_case_spec(**legacy_knobs, coupling_scheme=LEGACY_COUPLING_SCHEME)

    assert rebuilt.source.template == HG2007_TEMPLATE
    assert spec_config_digest(rebuilt) == spec_config_digest(hg2007_case_spec(**legacy_knobs))
