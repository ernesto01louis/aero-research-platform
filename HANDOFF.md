# Aero Research Platform — Handoff / Resume Notes

**Status: RETIRED — 2026-05-18.** Paused by the operator (Louis): the
project's compute footprint and CFD-expertise demands outgrew what this
homelab cycle could sustain (wall-resolved LES at ~30 h/run on an
8-core LXC, repeatedly disrupted by Proxmox host reboots). A fresh,
re-scoped version is being started in a separate effort. This file is
the resume point if the work is ever picked back up.

This is a **consumer** of the `ai-orchestrator` platform. It is not the
orchestrator. CFD runs execute on the `aero-research` LXC
(192.168.2.231) over SSH.

---

## 1. Git state (as of retirement)

`main` has only Stage 3. Two **local feature branches** carry the
Stage-4/5 work (pushed to `origin` at retirement for safekeeping; no
PRs were opened):

**`feat/stage4-alpha10-fix`** — 4 commits on top of `32b58aa`:
- `ecd2bf7` fix(meshing): relativeSizes false + absolute layer thickness
- `c90472c` chore(stage4.x): 01b rerun YAML drives the absolute-mode fix
- `2154d85` fix(meshing): grow prism stack past minFaceWeight + relaxed dict
- `bfc57c2` docs(stage4.x): record alpha=10 real root cause

**`feat/stage5-les-escalation`** — 5 commits on top of `32b58aa`:
- `c7f705d` feat(stage5): LES escalation — pimpleFoam/WALE template, pilot+sweep, burst
- `5452de3` / `530c572` / `f13e34f` / `85c8f27` — four iterative fixes to
  the LES transition setup (see §3).

All tests / ruff / mypy were green at each commit. Working trees clean.

---

## 2. Stage 4 — NACA 0012 baseline (verdict: PARTIAL)

alpha=0 PASSED long ago. alpha=10 was the open item. This session found
the **real root cause** (the prior Stage-4 diagnosis of "cold-start"
was secondary):

1. **`relativeSizes true`** in the snappyHexMesh addLayers dict made
   `firstLayerThickness` a *fraction* of the surface cell — the
   Stage-4.x "1e-7" tuning never actually changed the mesh. Fixed:
   absolute-length mode, 5e-6c first layer.
2. Even fixed, **`minFaceWeight 0.05`** rejects a 5e-6c layer sitting
   under the ~0.008c castellated cell (interpolation weight ~6e-4).
   With 15 layers addLayers extruded *zero* layers. Mitigated with 20
   layers / expansion 1.3 + a `relaxed` quality sub-dict → extrusion
   rose 0% → 77.6%, y+ 1167 → 514.

**Still PARTIAL.** snappyHexMesh addLayers cannot deliver a fully
wall-resolved high-Re airfoil boundary layer here — y+ ~514 is still
wall-function regime, Cl not recovered. **The structural fix is a
structured C-mesh generator** (the mesh the original brief asked for,
before Stage 4 deviated to snappy). `periodic_riblet_strip.py` proves
the codebase can write fully structured multi-block blockMesh; an
airfoil C-mesh module is the analogous, correct fix. See
`STAGE-4-OUTPUTS.md` (Stage-4.x section) for the full trail.

alpha=10 was **not** a Stage-6 blocker — Stage 6 runs at alpha=0.

---

## 3. Stage 5 — Bechert riblet replication: RANS FAIL → LES escalation

Stage 5 RANS k-omega SST FAILED (`STAGE-5-OUTPUTS.md`): measured peak
DR +0.2% vs Bechert +9.9% — isotropic eddy-viscosity closure cannot
carry the anisotropic protrusion-height mechanism (Luchini 1991). The
pre-registered escalation is wall-resolved LES.

### LES escalation — what was built (`feat/stage5-les-escalation`)
- `cfd/templates/flat-plate-riblet-pimpleFoam/` — LES case: pimpleFoam,
  WALE SGS, transient with adjustTimeStep/maxCo, backward ddt, PIMPLE.
- `campaigns/04-flat-plate-riblet-les-pilot.yaml` — 4-run pilot
  (s+ {15,17,20} riblet + 1 smooth baseline), local LXC.
- `campaigns/05-flat-plate-riblet-les-sweep.yaml` — full 9-point sweep,
  deferred to a SkyPilot cloud burst.
- `sky/openfoam-cpu.yaml` — CPU burst spec for the sweep.

### The transition saga — IMPORTANT, this is the hard-won knowledge
A wall-resolved Re_tau=180 channel LES kept **relaminarising**. Four
iterations to a working recipe:
1. White-noise IC → laminarised (grid-scale noise dissipates).
2. Coherent x-z rolls → laminarised — revealed the **spanwise domain
   was sub-minimal**: 4 riblet pitches = 60-80 wall units, below the
   ~100 wall-unit minimal-channel threshold (Jimenez & Moin 1991).
   Turbulence physically cannot self-sustain in a box narrower than one
   streak. Fixed: `--n-pitches-spanwise 8` (120-160 wall units).
3. Streamwise-vortex IC, 8-pitch box → still laminarised: x-uniform
   vortices make streaks but with no intermediate-scale streamwise-
   varying disturbance the streaks cannot break down — transient
   growth is transient.
4. **VALIDATED RECIPE** — broadband multi-mode IC (energy across
   several kx/ky/kz modes: x-uniform vortices for lift-up AND oblique
   sin(kx·x) modes for streak breakdown) + `div(phi,U) Gauss linear`
   (pure central; LUST's 25% upwind drained the marginal flow).
   **A smooth Re_tau=180 channel run with this recipe sustained
   turbulence** (pressure gradient ~1.0-1.2, fluctuating — confirmed
   over t=0→33).

The validated recipe lives in the committed
`flat-plate-riblet-pimpleFoam` template (final commit `85c8f27`):
- 8 spanwise pitches, n_x=60, broadband `setExprFieldsDict`,
  `div(phi,U) Gauss linear`, WALE, pimpleFoam.

### Where the pilot got to
The smooth baseline run reached t=33.8/40 turnover times (turbulent,
healthy). The riblet sweep (s+ 17/15/20) never started — the detached
pilot runner was killed by a Proxmox host reboot before the baseline
finished. **No DR numbers were produced.** Each LES run is ~30 h
wall-clock on the 8-core LXC.

---

## 4. Stage 6 — never started

NACA 0012 + suction-surface riblets, s+ sweep at alpha=0. Gated on the
Stage-5 LES pilot DR results (the recommended Stage-6 method is a
Luchini slip-length wall BC *calibrated from* the Stage-5 LES). Design
is in the plan file
`~/.claude/plans/we-are-continuing-development-compiled-salamander.md`.

---

## 5. Compute reality (the retirement reason)

- Wall-resolved LES at this Re is ~30 h/run on the 8-core aero LXC; the
  4-run pilot is ~5 days, the 9-point sweep months (cloud-burst territory).
- **Detached runs do not survive Proxmox host reboots** — there is no
  checkpoint/resume wired up. Any future LES campaign needs either a
  stable host or OpenFOAM restart-from-latest-time orchestration.
- The orchestrator's deterministic-run evidence path
  (`register_deterministic_run` → `build-bundle` → `evidence.verify`)
  works and was used for Stage 5 RANS — reuse it if resuming.

---

## 6. If resuming

1. **Stage 4**: write a structured airfoil C-mesh generator (analogous
   to `periodic_riblet_strip.py`) — abandons the snappyHexMesh addLayers
   dead-end. This also gives Stage 6 a clean airfoil mesh.
2. **Stage 5 LES**: the recipe in `flat-plate-riblet-pimpleFoam` is
   validated on a smooth channel — just run the 3 riblet pilot points
   (`campaigns/04-...-les-pilot.yaml`) on a host that won't reboot
   mid-run. Then compute DR vs Bechert in
   `notebooks/02-bechert-1997-replication.ipynb`, register the runs,
   build the evidence bundle, write STAGE-5-LES-OUTPUTS.md.
3. **Stage 6**: only after Stage 5 LES gives the s+→DR calibration.
