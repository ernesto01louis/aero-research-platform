---
# Required frontmatter — scripts/check_handoff_exists.sh parses these.
stage: NN                                  # e.g. 01
stage_name: "Stage NN — <name>"            # e.g. "Stage 01 — Scaffolding & Conventions"
status: complete                           # complete | partial | blocked
date_started: YYYY-MM-DD
date_completed: YYYY-MM-DD
session_duration_hours: 0                  # rounded to nearest 0.5
claude_code_version: ""                    # output of `claude --version`
model: claude-opus-4-7
git_sha_start: ""                          # 40-char SHA at session start
git_sha_end: ""                            # 40-char SHA at session end (post-handoff commit)
stage_tag: v0.0.NN
next_stage: NN+1
next_stage_name: "Stage NN+1 — <name>"
---

# Stage NN — <Name> — DONE YYYY-MM-DD

> Auto-loaded by the NEXT session as "BEFORE YOU START — READ". Keep
> sections in this order so future-you can scan. Be terse and concrete;
> the diff is in git.

## 1. Deliverables status

| # | Deliverable (verbatim from stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | <e.g. "CLAUDE.md authored"> | ✅ | — |
| 2 | <next> | ⚠️ | partial — see Deviations |
| 3 | <next> | ❌ | blocked — see Open items |

(✅ = done, ⚠️ = partial, ❌ = not done / blocked)

## 2. Decisions made

Decisions taken in this session, with rationale and **rejected
alternatives** (the why-we-didn't is as important as the why-we-did).

- **<decision>** — chose X over Y because Z. Rejected: A (because reason),
  B (because reason).
- ...

## 3. Deviations from the stage plan

Where the executed work differs from the stage prompt. Be honest;
partial work counts as a deviation.

- ...

## 4. Environment / dependency / schema changes

Concrete diffs that affect future sessions:

- `pyproject.toml` extras added: ...
- Postgres tables/roles/DBs created on LXC 202: ...
- MinIO buckets created: ...
- Container SHA additions in `containers/SHA256SUMS`: ...
- DVC tracked files added: ...

## 5. CI/CD changes

- Workflows added: ...
- Workflows modified: ...
- Required status checks on `main` added/removed: ...
- Branch protection diffs: ...

## 6. Gotchas discovered

Surprises future sessions need to know about. Be specific.

- ...

## 7. Open items for the next stage (and beyond)

Concrete next-action items.

- **Stage NN+1**: ...
- **Stage NN+2+**: ...

## 8. Pointers for the next session

- **Read first:** ...
- **Do not re-read** (already in CLAUDE.md / prior handoffs): ...
- **Run first to verify the world**: e.g.
  `aero vv report --latest`, `gh run list --limit 5`,
  `psql -c 'SELECT 1' postgresql://...`

## 9. Artifacts produced

Narrative index of what this stage produced. Git log is authoritative;
this is the prose summary.

- `<path>` — what it is, why it's here
- ...

## 10. Confidence / risk note

- **High confidence:** ...
- **Medium confidence:** ... (what might bite later)
- **Low confidence / bus factor:** ... (what only the operator knows)
- **Outstanding risks:** ...
