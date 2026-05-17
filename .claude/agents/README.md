# `.claude/agents/`

Project-scoped agent definitions for Claude Code subagents (per
[Claude Code docs](https://docs.claude.com/en/docs/claude-code/sub-agents)).

Empty as of Stage 01. Future stages may add specialized agents:

- **Stage 05+** — a `vv-triage` agent that investigates failing V&V
  cases (parses MLflow run, mesh, BCs, suggests a hypothesis)
- **Stage 09+** — a `surrogate-trainer` agent that runs hyperparam sweeps
  on RunPod under the cost cap
- **Stage 14+** — a `cae-design` agent that wraps the NeMo Agent Toolkit
  with this project's MCP tool surface

Each agent definition is a markdown file with frontmatter (`name`,
`description`, `tools`, optional `model`) plus a body that is the system
prompt.

See the project root `CLAUDE.md` for invariants every agent must obey
(provenance, fail-loud, no-secrets, certificate-of-validity).
