"""A two-participant preCICE "solver dummy" — the infrastructure pre-flight (gate I1).

This is the **only** place in the repo that imports ``pyprecice``, and it never runs on
the host: it runs *inside* the SIF, before any physics, and answers in seconds the
questions that would otherwise be answered eight hours into a coupled campaign:

* does ``apptainer exec`` work for this image at all;
* does ``MPI_Init`` succeed inside the unprivileged LXC (the preCICE packages are
  MPI-enabled even though this case's m2n is sockets);
* can two containers actually connect over the socket m2n and exchange data;
* does ``--no-home`` break anything;
* and — because it is launched through the real
  :func:`aero.adapters.precice.launcher.launch_coupled` — is the supervisor script
  correct.

The import is function-local by design: ``aero.adapters.precice`` must stay importable
with no extras installed (Invariant 1, enforced by the ``import-platform-only`` CI job),
so ``pyprecice`` may not appear at module scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_CONFIG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" ?>
<precice-configuration>
  <log>
    <sink filter="%Severity% > debug" enabled="true" />
  </log>

  <data:vector name="Probe" />

  <mesh name="A-Mesh" dimensions="2">
    <use-data name="Probe" />
  </mesh>
  <mesh name="B-Mesh" dimensions="2">
    <use-data name="Probe" />
  </mesh>

  <participant name="A">
    <provide-mesh name="A-Mesh" />
    <receive-mesh name="B-Mesh" from="B" />
    <write-data name="Probe" mesh="A-Mesh" />
    <mapping:nearest-neighbor direction="write" from="A-Mesh" to="B-Mesh"
                              constraint="consistent" />
  </participant>

  <participant name="B">
    <provide-mesh name="B-Mesh" />
    <read-data name="Probe" mesh="B-Mesh" />
  </participant>

  <m2n:sockets acceptor="A" connector="B" exchange-directory="." />

  <coupling-scheme:serial-explicit>
    <time-window-size value="0.1" />
    <max-time value="1.0" />
    <participants first="A" second="B" />
    <exchange data="Probe" mesh="B-Mesh" from="A" to="B" />
  </coupling-scheme:serial-explicit>
</precice-configuration>
"""


def write_solverdummy_config(dest: Path) -> Path:
    """Write the minimal serial-explicit config the dummies couple over. Pure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
    return dest


def run_solverdummy(*, participant: str, config: Path, mesh_size: int = 3) -> int:
    """Run one dummy participant to completion. Executed INSIDE the SIF.

    Returns 0 on a clean coupled finish; raises otherwise. Requires ``aero[precice]``
    (``pyprecice``), which is why the import is function-local.
    """
    try:
        import precice  # lazy by design (Invariant 1) -- must not be a module-scope import
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "pyprecice is not installed. The preCICE solver dummy runs inside the "
            "precice-fsi SIF; on a host, install the extra: pip install -e '.[precice]' "
            "(note: pyprecice is sdist-only and needs the preCICE C++ headers and MPI "
            "development headers to build)."
        ) from exc

    if participant not in ("A", "B"):
        raise ValueError(f"solverdummy participant must be 'A' or 'B', got {participant!r}")
    mesh_name = f"{participant}-Mesh"

    interface: Any = precice.Participant(participant, str(config), 0, 1)
    dimensions = interface.get_mesh_dimensions(mesh_name)
    coordinates = [[float(i), 0.0][:dimensions] for i in range(mesh_size)]
    vertex_ids = interface.set_mesh_vertices(mesh_name, coordinates)

    interface.initialize()
    step = 0
    while interface.is_coupling_ongoing():
        dt = interface.get_max_time_step_size()
        if participant == "A":
            payload = [[float(step), 0.0][:dimensions] for _ in range(mesh_size)]
            interface.write_data(mesh_name, "Probe", vertex_ids, payload)
        else:
            interface.read_data(mesh_name, "Probe", vertex_ids, dt)
        interface.advance(dt)
        step += 1
    interface.finalize()

    if step == 0:
        raise RuntimeError(
            f"solverdummy {participant}: the coupling finished without advancing a single "
            "time window — the participants connected but exchanged nothing"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used inside the SIF: ``python -m ... --participant A --config c.xml``."""
    import argparse  # local: keeps the module import cheap

    parser = argparse.ArgumentParser(description="preCICE solver dummy (aero pre-flight gate I1).")
    parser.add_argument("--participant", required=True, choices=("A", "B"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mesh-size", type=int, default=3)
    args = parser.parse_args(argv)
    return run_solverdummy(
        participant=args.participant, config=args.config, mesh_size=args.mesh_size
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
