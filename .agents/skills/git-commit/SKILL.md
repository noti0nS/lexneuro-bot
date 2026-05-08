---
name: git-commit
description: >
  Create a conventional git commit with a 72-char-max title and a body
  listing changed files. Automatically stages (`git add`) and commits.
  Trigger: "commit", "make a commit", "git commit", "create commit".
---

## When to Run

Use this skill when the user asks you to create a git commit. Do NOT run it unprompted — the user must explicitly request a commit.

## Commit Workflow

### 1. Inspect the working tree

Run in parallel:

- `git status` — staged, unstaged, and untracked files
- `git diff` — unstaged changes
- `git diff --cached` — staged changes
- `git log --oneline -5` — recent commit style reference

### 2. Determine `type` and `scope`

| Type       | When to use                                       |
|------------|---------------------------------------------------|
| `feat`     | A new feature or user-facing capability           |
| `fix`      | A bug fix                                         |
| `chore`    | Tooling, config, dependencies, no user impact     |
| `refactor` | Code change with no behavior change               |
| `docs`     | Documentation only                                |
| `test`     | Adding or fixing tests                            |
| `perf`     | Performance improvement                           |
| `style`    | Formatting, lint, whitespace (no logic change)    |

**Scope** is the primary area affected. Derive it from the file paths:

- Files under `src/commands/` → scope = `commands` (or the specific command name like `pesquisa`)
- Files under `src/helpers/` → scope = `helpers` (or the specific helper name like `llm`)
- `src/bot.py` → scope = `bot`
- `src/config.py` → scope = `config`
- `tests/` only → scope = `tests`
- `pyproject.toml` / `uv.lock` / `.python-version` → scope = `deps`
- `.github/` → scope = `ci`
- Changes spanning 3+ unrelated areas → omit scope (just `type: message`)

### 3. Craft the commit message

**Title** (max 72 chars, imperative mood):
```
<type>(<scope>): <short summary>
```
or without scope:
```
<type>: <short summary>
```

**Body** — a bullet list of files changed with a brief note of what was done in each. Do NOT repeat the short summary.

```
- `path/to/file`: what changed (add, update, remove, rename)
- `path/to/file2`: what changed
```

**Full message template**:
```
<type>(<scope>): <summary>

- `path/to/file`: description of change
- `path/to/file2`: description of change
```

### 4. Stage and commit

```
git add <files>       # only what should be committed
git commit -m "<message>"
```

- If the user asked to commit **all** changes, use `git add -A`.
- If only specific files, add only those.
- Never add `.env`, `config.yaml`, `credentials.json`, or other secret files.

### 5. Commit rules

- Title: max 72 characters, imperative, no period at end
- Body: blank line after title, bullet list of files with `- ` prefix
- Do NOT use `--no-verify`, `--amend`, `-n`, or any flag that skips hooks
- If a pre-commit hook rejects the commit, fix the issue and create a new commit (never amend)
- After committing, run `git status` to verify clean state
