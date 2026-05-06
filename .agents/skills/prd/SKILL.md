---
name: prd
description: >
  Build a Product Requirements Document for a new LexNeuro slash command. Follows the
  canonical PRD structure (Overview → Technical Architecture → Edge Cases → Testing).
  Output goes to `prd/<command-name>.md`. Trigger: "create PRD", "write PRD",
  "spec out <command>", "PRD for /command".
---

## When to Run

Use this skill when asked to create a new PRD (or update an existing one) for any LexNeuro slash command. The canonical templates live at `prd/cronograma.md` and `prd/pesquisa.md` — study both before writing.

## PRD Structure (ordered, all sections required)

### 1. Title

```markdown
# PRD: `/command` — Short Description (3-8 words)
```

### 2. Overview

Purpose (1-2 sentences). Target users (1 sentence). Do NOT re-describe the feature flow here — that goes in User Flow.

```markdown
## Overview

### Purpose
Brief purpose.

### Target Users
Who uses this.
```

### 3. User Flow

Numbered ASCII-art flow showing every step the user takes from slash-command invocation to final output. Include what the bot sends at each step.

```
1. User invokes /command ...
2. Bot responds with ...
3. User ...
4. Bot ...
```

### 4. Slash Command Parameters

Table with columns: Parameter, Type, Required, Description.

Every parameter, every type (STRING, INTEGER, BOOLEAN, ATTACHMENT, etc.). Add a note after the table if any parameter type requires a workaround (e.g., no native date type in Discord).

### 5. Core Feature Specifications

One subsection per major feature. Each subsection describes behavior, data transformations, and constraints. Use tables for config keys, option constraints, or decision matrices.

Sections vary by feature but typically include:
- Calendar / window computation (if applicable)
- UI components (select menus, buttons, views)
- LLM prompt design (system prompt + user message template)
- LLM call pattern (streaming vs non-streaming, tool calls, heartbeats)
- File output / delivery strategy (if applicable)

Include inline examples of prompts, output formats, and UI mockups.

### 6. Configuration

```yaml
# config-example.yaml additions
command_name:
  key1: default
  key2: default
```

List every config key with its default and purpose.

### 7. Files to Create/Modify

Table with columns: File, Action. List every file touched, even if the change is one import line. Mark files with "Create" or "Edit".

### 8. Edge Cases & Error Handling

Table with columns: Case, Behavior. Cover ALL of:
- Invalid/empty inputs
- Future/past constraint violations
- Discord limits exceeded (select options, message length, file size)
- UI timeouts
- Permission denials
- LLM errors (content filter, max tokens, provider errors, empty output)
- Fallback paths when primary path fails

### 9. Example Interaction

ASCII-art or annotated transcript showing a full happy-path interaction. Include what the user types, what the bot shows, and expected output content.

### 10. Testing

```markdown
Test file: `tests/test_command.py`
```

Bulleted list of test cases. Each is a function name + 1-line description. Mirror the edge cases table.

### 11. Out of Scope & Future Enhancements

```markdown
### Out of Scope (v1)
- Thing not included

### Future Enhancements
- Thing to add later
```

## Writing Rules

- **Match the codebase's language**: If the bot speaks Portuguese, the PRD's user-facing strings and command descriptions should be in Portuguese. Technical sections stay in English or mirror existing PRDs.
- **Use existing imports and helpers**: Reference `src/helpers/*`, `src/config.py`, `src/helpers/llm.py`, `src/prompts/*` — don't invent new utility modules unless the feature truly needs one.
- **Config is hot-reloaded**: Every PRD must mention that config is fetched via `await asyncio.to_thread(get_config)` on each invocation (no caching).
- **Follow the LLM call pattern from pesquisa.py**: Non-streaming with `await_task_with_heartbeats`. If streaming, explain why.
- **Discord constraints**: Select menus max 25 options, labels ≤100 chars, values ≤100 chars. Message content ≤2000 chars (plain) or ≤4096 (embed description). File attachments ≤8MB (Discord) or 25MB (Nitro).
- **Permissions model**: Check `user_has_permission()` if the command requires gating.
- **No new dependencies without justification**: If a new pip package is needed, add it to `pyproject.toml` in the Files table.

## Output

Write the PRD to `prd/<command-name>.md`. Do NOT write to `docs/` or the repo root. After writing, verify no conflicts with existing PRDs in the same directory.
