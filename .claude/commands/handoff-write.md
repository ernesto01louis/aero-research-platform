---
description: Write the post-stage handoff for the current stage from the template
allowed-tools: Read, Write, Edit, Bash
argument-hint: <slug>
---

# /handoff-write <slug>

Writes a post-stage handoff for the current stage. Usage:

```
/handoff-write scaffolding-and-conventions
```

## What this does

1. Reads `.aero-stage` to determine the current stage number NN.
2. Reads `docs/handoffs/_template.md` for the canonical template.
3. Creates `docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md` populated
   with:
   - Frontmatter computed from session state (`git rev-parse HEAD`,
     `claude --version`, `date -I`, `whoami`, etc.)
   - DELIVERABLES checklist from the stage prompt
   - Decision-log + rationale (drafted by the model; operator reviews)
   - Open items for the next stage
4. Reminds operator to run `scripts/regenerate_status.sh` and PR the
   handoff before tagging.

## Frontmatter validation

The Stop hook (`scripts/check_handoff_exists.sh`) requires:
- `stage`, `stage_name`, `status` (complete|partial|blocked)
- `date_completed` (ISO date)
- `git_sha_end` (40-char SHA)

Other recommended frontmatter fields per the template:
- `date_started`, `session_duration_hours`
- `claude_code_version`, `model`
- `git_sha_start`, `stage_tag`, `next_stage`, `next_stage_name`
