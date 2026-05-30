"""JAX-Fluids native case-file emitters.

JAX-Fluids consumes two JSON files per case:

* ``numerical_setup.json`` — solver scheme (Riemann solver, time integrator,
  reconstruction).
* ``case_setup.json`` — domain, initial condition, boundaries, output cadence.

Stage-08 emits both for :class:`~aero.adapters.jax_fluids.schemas.JaxFluidsShockTubeSpec`;
the :class:`~aero.adapters.jax_fluids.schemas.JaxFluidsMeshFileSpec` path
copies pre-existing files from the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

from aero.adapters.jax_fluids.schemas import JaxFluidsShockTubeSpec


def write_shock_tube_case_files(
    target_dir: Path,
    spec: JaxFluidsShockTubeSpec,
) -> tuple[Path, Path]:
    """Write ``numerical_setup.json`` + ``case_setup.json`` for Sod's tube.

    Returns ``(numerical_path, case_path)``. The returned paths sit inside
    ``target_dir``; the adapter binds that directory into the SIF as
    ``/case`` at exec time.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    numerical_path = target_dir / "numerical_setup.json"
    case_path = target_dir / "case_setup.json"

    # Numerical setup: HLLC Riemann solver + WENO5 reconstruction + RK3 time
    # integrator. JAX-Fluids' canonical settings for Sod's tube.
    numerical = {
        "conservatives": {
            "halo_cells": 3,
            "time_integration": {
                "integrator": "RK3",
                "CFL": spec.cfl,
            },
            "convective_fluxes": {
                "convective_solver": "GODUNOV",
                "godunov": {
                    "riemann_solver": "HLLC",
                    "reconstructor": "WENO5-JS",
                    "split_reconstruction": False,
                },
            },
            "dissipative_fluxes": {"reconstruction_stencil": "CENTRAL2"},
        },
        "active_physics": {
            "is_convective_flux": True,
            "is_viscous_flux": False,
            "is_heat_flux": False,
            "is_volume_force": False,
        },
        "active_forcings": {},
        "output": {
            "output_period": spec.monitor_dt,
            "is_xdmf": False,
            "is_active": True,
        },
    }
    numerical_path.write_text(json.dumps(numerical, indent=2))

    # Case setup: 1D unit domain, Sod's initial condition, Neumann boundaries.
    case = {
        "general": {
            "case_name": spec.name,
            "end_time": spec.t_end,
            "save_path": "./out",
            "save_dt": spec.monitor_dt,
        },
        "domain": {
            "x": {
                "cells": spec.n_cells,
                "range": [0.0, 1.0],
            },
            "y": {"cells": 1, "range": [0.0, 1.0]},
            "z": {"cells": 1, "range": [0.0, 1.0]},
            "decomposition": {"split_x": 1, "split_y": 1, "split_z": 1},
        },
        "boundary_conditions": {
            "east": {"type": "ZEROGRADIENT"},
            "west": {"type": "ZEROGRADIENT"},
            "north": {"type": "PERIODIC"},
            "south": {"type": "PERIODIC"},
            "top": {"type": "PERIODIC"},
            "bottom": {"type": "PERIODIC"},
        },
        "initial_condition": {
            "primitives": {
                "rho": "lambda x, y, z: 1.0 * (x < 0.5) + 0.125 * (x >= 0.5)",
                "u": "lambda x, y, z: 0.0",
                "v": "lambda x, y, z: 0.0",
                "w": "lambda x, y, z: 0.0",
                "p": "lambda x, y, z: 1.0 * (x < 0.5) + 0.1 * (x >= 0.5)",
            }
        },
        "material_properties": {
            "equation_of_state": {
                "model": "IdealGas",
                "specific_heat_ratio": 1.4,
                "specific_gas_constant": 1.0,
            },
            "transport": {
                "dynamic_viscosity": {"model": "CUSTOM", "value": 0.0},
                "bulk_viscosity": 0.0,
                "thermal_conductivity": {"model": "CUSTOM", "value": 0.0},
            },
        },
    }
    case_path.write_text(json.dumps(case, indent=2))
    return numerical_path, case_path
