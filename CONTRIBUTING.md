# Contributing to aero-research-platform

## Ground rules

1. **Conventional Commits.** Subject line is `<type>: <imperative summary>` where `type` is one of `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `style`, `perf`, `build`, `ci`. Body explains *why*, not *what*.
2. **Branches:** `<type>/<short-slug>`. Never commit to `main`.
3. **PRs only.** `main` is protected — required CI checks + one approving review. Admin bypass is enabled so the solo maintainer can self-merge after CI is green; do not bypass on substantive changes.
4. **No domain leakage.** This repo is *aerodynamics*. RF, music, protein folding, etc. get their own consumer repos.
5. **No orchestrator-internal imports.** The only allowed import from the orchestrator side is `from ai_orchestrator_client import …`. CI does not (yet) enforce this with a source-text guard; future commits may.

## Development workflow

1. **Fork or branch.** For solo work, branch off `main`:
   ```sh
   git checkout -b feat/airfoil-cmesh
   ```

2. **Install the package in editable mode** with dev deps:
   ```sh
   python3.11 -m venv .venv && source .venv/bin/activate
   pip install -e '.[dev]'
   ```

   **Local SDK override** — if you're iterating on `ai-orchestrator-client` at the same time, install it editable AFTER the package install (the project pin yields to whichever is installed):
   ```sh
   pip install -e /opt/ai-orchestrator-client
   ```

3. **Make your change.** Add tests under `tests/`.

4. **Run the local CI loop:**
   ```sh
   ruff check .
   mypy aero_research_platform
   pytest -q
   ```

5. **Commit + push + open a PR:**
   ```sh
   git add <files>
   git commit -m "feat: add airfoil C-grid mesher"
   git push -u origin feat/airfoil-cmesh
   gh pr create --fill
   ```

6. **Wait for CI.** Merge once green. Use `gh pr merge --squash --auto` to merge as soon as CI passes.

## What needs a PR vs. what can land direct

| Change type | Path |
|---|---|
| Substantive code (anything in `aero_research_platform/`) | PR + CI + review |
| New campaign YAML | PR + CI |
| Doc-only edits (README, ROADMAP, CONTRIBUTING, VISION) | PR + CI (still cheap; keeps the log clean) |
| Typo fixes | PR + admin bypass acceptable |
| Stage-output files in the repo root (`STAGE-N-OUTPUTS.md`) | PR or direct on `main`; these are historical artifacts, not source code |

## Code review check-list

When reviewing your own PR (yes, that's the workflow):

- [ ] CI green.
- [ ] No orchestrator-internal imports.
- [ ] No domain leakage *into the orchestrator* via the SDK (the orchestrator never receives an aero-shaped object — it only receives `CampaignCreate` shapes).
- [ ] Tests cover the new code's *contract*, not its *implementation*.
- [ ] `pyproject.toml` deps added only if they're in the [in-scope list in CLAUDE.md](CLAUDE.md#in-scope-libraries).
- [ ] `ROADMAP.md` checkmark added for any item that just shipped.

## License

By contributing, you agree your contributions are licensed under [Apache-2.0](LICENSE).
