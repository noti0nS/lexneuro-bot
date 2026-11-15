---
name: deps-pr-triage
description: >
  Analyze open dependency and security PRs (e.g., Dependabot) one by one,
  apply compatible bumps to pyproject.toml / uv.lock / Dockerfile, verify with
  tests and static analysis, commit and push to main, and close PRs with their
  remote branches. Trigger: "dependency PRs", "dependabot PRs", "update libs",
  "bump libs", "triage PRs", "security alerts".
---

## When to Run

Use this skill when the user asks to analyze, apply, test, and clean up open dependency or security PRs (typically Dependabot PRs) directly on `main`.

## Workflow

### 1. Inventory PRs, Security Alerts, and Baseline

1. Confirm a clean `main` branch and prune stale refs:
   ```bash
   git status
   git fetch --prune
   ```
2. List open PRs and their changed files:
   ```bash
   gh pr list --state open --json number,title,headRefName,files
   ```
3. Check open Dependabot security alerts (if enabled on the repo):
   ```bash
   gh api "repos/{owner}/{repo}/dependabot/alerts?state=open"
   ```
4. Check currently locked versions in `uv.lock` (using Python `tomllib`) and installed versions in `.venv` (`importlib.metadata`) so you know which PRs are already superseded.
5. Run the baseline test and lint suite before making changes:
   - Windows: `.venv\Scripts\python.exe -m pytest`, `.venv\Scripts\python.exe -m basedpyright src tests`, `.venv\Scripts\ruff.exe check .`, `.venv\Scripts\ruff.exe format --check .`
   - Linux/macOS: `uv run pytest`, `uv run basedpyright src tests`, `uv run ruff check .`, `uv run ruff format --check .`

### 2. Analyze Each PR One by One

Classify every open PR before editing anything:

| Category | How to Check | Action |
|---|---|---|
| **Already superseded** | Target version (or newer) is already in `uv.lock` and no `pyproject.toml` floor change is requested | Skip code edits; close PR as superseded. |
| **Security / lockfile bump (`uv.lock`)** | Run `uv lock --upgrade-package <pkg> --dry-run` | Upgrade if compatible; check major-version breaking changes if crossing a major version. |
| **Floor bump (`pyproject.toml`)** | Check if `uv.lock` already has `>= target` (or upgrade it). For **major bumps** (e.g., `openai 2.x -> 3.x`), `rg` usages in `src/` and `tests/` for breaking API changes | Update `pyproject.toml` floor. |
| **Runtime / `Dockerfile` bump** | Check `Dockerfile` build steps (`pip install -r requirements.txt` with no C/Rust compiler). Query PyPI JSON API for target `cp3XX` wheels on native packages (especially `onnxruntime`, `numpy`, `pillow`) | **Only bump** if all required binary packages publish wheels (or buildable sdists) for the target Python version; otherwise **reject** and keep current base image. |

### 3. Apply Bumps and Sync

1. Edit `pyproject.toml` (and `Dockerfile` only if verified safe) for all approved PRs.
2. Upgrade targeted packages in `uv.lock` and sync `.venv`:
   ```bash
   uv lock --upgrade-package <pkg1> --upgrade-package <pkg2>
   uv sync
   ```

### 4. Test and Verify

1. Re-run the full verification suite after final edits:
   - `pytest` (all tests must pass)
   - `basedpyright src tests` (0 errors, 0 warnings)
   - `ruff check .`
   - `ruff format --check .`
2. Run a quick Python import/smoke test for any library that crossed a major version or had a security upgrade (e.g., importing `src.bot` and exercising the upgraded package).

### 5. Commit and Push

Follow the `git-commit` skill conventions:
```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): <short summary>" -m "- pyproject.toml: ..." -m "- uv.lock: ..."
git push origin main
```

### 6. Close PRs and Delete Branches

Close every triaged PR with `--delete-branch` and an accurate comment:

- **Applied**: `"Applied on main in <commit-sha> and verified with pytest, basedpyright, and ruff."`
- **Superseded**: `"Already superseded on main in uv.lock."`
- **Incompatible / Rejected**: `"Not applied: <specific reason, e.g., onnxruntime lacks cp315 wheels on PyPI>."`

```bash
gh pr close <number> --delete-branch --comment "<reason>"
```

Finally, verify `gh pr list --state open` returns empty and `git fetch --prune` is clean.
