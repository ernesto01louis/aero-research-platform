# `docs/sota/`

State-of-the-art literature review material for `aero-research-platform`.

- **Pass 2 — SOTA Literature Review (2024–2026)** lands here once the
  operator commits it. Encyclopedic across 24 domains; the canonical
  reference for current best practices, dead-end avoidance, and
  citation-ready prior art.

Key findings to keep at hand (full pass committed when operator provides):

- Hybrid RANS-LES + WMLES is current practical SOTA; vanilla PINNs are
  a dead end for turbulent flows; neural operators (Transolver, DoMINO,
  FIGConvNet, GeoTransolver) are the frontier.
- Industry consolidation: Synopsys-Ansys ($35B, July 2025); Siemens-
  Altair (~$10B, March 2025); Cadence Fidelity now bundles NUMECA +
  Pointwise + Cascade.
- Funding: Neural Concept $100M Series C; Luminary Cloud $72M Series B;
  PhysicsX $155M Series B; CoreWeave acquired Monolith (Nov 2025).
- Agentic CFD is working: ChatCFD 82.1% success on certain task classes;
  MetaOpenFOAM, OpenFOAMGPT, Foam-Agent 2.0.
- AeroSHARK riblets validated in-flight (Lufthansa Group, 22 aircraft).

This directory is the substrate for Stage 15's literature mining
pipeline; the `auto_cite` workflow extends the curated index by
appending discovered references with citation provenance.
