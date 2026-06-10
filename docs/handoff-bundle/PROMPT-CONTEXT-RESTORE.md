# Context Restoration — aero-research-platform (optimizer mission)

**Paste or attach this into a fresh chat/session to get current on the project.** It is the
single "start here" pointer. It supersedes the original context-restore prompt (archived at
`archive/original-roadmap/PROMPT-CONTEXT-RESTORE.md`), which describes a do-everything
roadmap that has been **cut**. Read the *current* documents below; do **not** treat anything
under `docs/handoff-bundle/archive/` as guidance.

---

## What the platform is (current, governing)

`aero-research-platform` is a **hypothesis-driven aerodynamic shape/topology optimizer**:
plug in geometry (parametric first; CAD/STL/3MF later), define an aerodynamic objective, and
the platform returns an **improved, CFD-verified design** — CFD is the ground truth. The
forward CFD + UQ + provenance stack is the *foundation that makes claimed improvements
trustworthy*, not the product. **Flapping-wing aerodynamics is the single flagship
demonstration domain.** Adopted by **ADR-013** (2026-06-10).

## Read these first (in order)

1. **`CLAUDE.md`** — invariants + Hard Rules 1–17. The mission ones (added at the refocus):
   12 IMPROVEMENT-EXCEEDS-UNCERTAINTY, 13 NO-SURROGATE-ON-FOREIGN-DATA, 14
   CFD-VERIFIED-OPTIMUM-ONLY, 15 VALIDATE-AGAINST-EXPERIMENT, 16 RESULTS-MUST-TRAVEL,
   17 SCOPE-GATE.
2. **`docs/handoff-bundle/00-MISSION-AND-SCOPE.md`** — the **governing scope** (the optimizer
   mission; flapping flagship; what's cut). Where it conflicts with anything, it governs.
3. **`docs/handoff-bundle/README-handoff.md`** — the current **Stage 10–20 map** + cross-stage
   guardrails. This replaces the original 16-stage roadmap.
4. **`CONSTITUTION.md`** — Invariants 1–9 are live; **Invariants 10 (improvement-exceeds-U95)
   + 11 (no-foreign-data)** are in the 72 h-review PR (ADR-015) and ratify ~2026-06-13.
5. **`docs/adrs/`** — esp. ADR-013 (mission refocus), ADR-014 (budget tiers, $150 baseline),
   ADR-015 (Invariants 10/11), ADR-016 (FSI structural-solver strategy).
6. **`.claude/rules/`** — `flapping-validation-ladder.md`, `optimization-integrity.md`
   (load when touching `aero/vv/` or `aero/optimize/`), plus the originals.
7. The **latest `docs/handoffs/STAGE-NN-*-DONE-*.md`** for what the previous session did.
8. **`docs/architecture/BRIEFING-architecture-review-for-independent-challenge.md`** — the
   architecture briefing (non-normative input, partially adopted per ADR-013).

## What was CUT or demoted (do not revive without a new ADR — SCOPE-GATE)

- **Automotive surrogate zoo** (DoMINO/Transolver/FIGConvNet/X-MGN on DrivAerML) + **MoE** —
  CUT. Surrogates train only on the platform's own validated CFD (Invariant 11). The DoMINO
  code/SIF/353 GiB DrivAerML are **frozen, not deleted** — do not touch without `approved`.
- **Riblets / shark-skin** — demoted to one **example**, not a flagship. **PyFR/NekRS/SU2/
  JAX-Fluids are frozen-optional** (SU2 = post-v0.1.0 adjoint seed).
- **DPW-7/HLPW-5** V&V — CUT (NASA TMR kept). **NeMo agent layer + literature miner** —
  deferred indefinitely. **Covalent / multi-cloud router** — deferred.

> ⚠ **Scope-drift hazard.** `docs/handoff-bundle/archive/` holds the superseded planning docs
> — the original "do-everything" brief, the original two-flagship mission draft, the original
> Stage 01–16 prompts, and two architecture reviews (one of which, the "compass artifact,"
> argues "build a thesis, not a platform" — the **opposite** of the current mission). They are
> kept for provenance only. **A session that takes them as guidance will revive cut scope.**
> Always prefer `00-MISSION-AND-SCOPE.md` + `README-handoff.md`. SCOPE-GATE (Hard Rule 17)
> gates effort to the optimizer + flapping flagship.

## Current state (update this line each stage)

Stage 09 (DoMINO baseline) is **closed**; **v0.0.9 tagged** on `main`. The optimizer-mission
refocus is merged. **Stage 10** (V&V-debt hard go/no-go + the output-validity bar) is the next
work; its first artifact, `aero/vv/reportable.py` (the `ReportableResult` / `ImprovementClaim`
/ `OptimizationResult` schema for Invariant 10), is on PR #16. Constitution Invariants 10/11
(PR #15) ratify ~2026-06-13.

## How to behave

- **Search first** for anything time-sensitive (solver/library versions, GPU pricing, current
  SOTA) — don't answer from memory.
- **Propose first, execute later** for destructive/persistent ops; wait for literal `approved`.
- **Every reported improvement** must clear `delta > k·U95` and be **CFD-verified** (Hard
  Rules 12, 14). **Validate against experiment/DNS**, not CFD-vs-CFD alone (Hard Rule 15).
- Defer to `00-MISSION-AND-SCOPE.md` + the ADRs on scope; if something there is wrong, propose
  an update via a new ADR — don't silently override.
