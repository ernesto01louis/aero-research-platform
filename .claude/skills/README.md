# `.claude/skills/`

Project-scoped Claude Code skills (per
[Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills)).

Empty as of Stage 01. Likely future skills:

- **`run-vv-case`** — wraps `aero vv run --case <name>` with provenance-
  tag validation
- **`submit-runpod`** — wraps the Stage 13 cost-routed executor for
  one-shot job submission
- **`mlflow-query`** — searches the four-tuple-indexed MLflow store
- **`write-adr`** — drafts an ADR from the MADR template at
  `docs/adrs/_template.md`

Each skill is a directory with a `SKILL.md` describing the trigger
phrases and the tool surface. Skills compose with the rules in
`.claude/rules/` — skills are *capabilities*; rules are *constraints*.
