# AGENTS.md

## Quick commands

```bash
uv run pytest                          # run all tests
uv run pytest tests/test_bot_utils.py  # run one file
uv run basedpyright src tests          # typecheck
uv run ruff check .                    # lint
uv run ruff format --check .           # check formatting
uv run python main.py                  # run the bot

- `main.py` → `src/main.py:run()` → `src/bot.py:create_discord_bot()` — this is the bot lifecycle.
- `main.py` in the repo root is a dead stub, not the entrypoint.
- `src/bot.py` owns the `on_message` handler, `MsgNode` cache, reply chains, LLM streaming, and response splitting. All slash commands are registered from there.

## Package layout

| Directory | Purpose |
|---|---|
| `src/bot.py` | Core bot: message routing, reply chains, LLM streaming |
| `src/config.py` | YAML config loading, OpenAI client factory, config masking |
| `src/commands/` | Slash commands: `/model`, `/abnt`, `/pesquisa`, `/cronograma` |
| `src/prompts/` | System prompts + markdown reference files loaded at runtime |
| `src/helpers/` | Async heartbeat, content parsing, DOCX/ODT I/O, web search, UI, LLM |

## Key invariants

- **Config is hot-reloaded** on every message/command via `asyncio.to_thread(get_config)`. Never cache config values across requests.
- **Provider/model format**: `provider/model` string, e.g. `openai/gpt-5`. Split on `/` in `get_openai_config()`. Vision models detected by checking if the model name string contains any of `VISION_MODEL_TAGS`.
- **`config.yaml` is gitignored** — never commit real config. Template is `config-example.yaml`.
- **`requirements.txt` does not exist** (README mentions it but it's stale/missing). Use `uv` with `pyproject.toml`.

## Dev environment

- **Python 3.13+** required (`.python-version`).
- Package manager: `uv` (`uv.lock` committed, `pyproject.toml` has dependencies).
- **All commands go through `uv run`**, e.g. `uv run pytest`, `uv run python ...`. Never use a bare host `python` — it may not exist or be the wrong version. `uv` manages the isolated `.venv/`.
- Type checker: **basedpyright** (`pyrightconfig.json`).
- Linter/formatter: **ruff**.

## Testing conventions

- Tests use **dataclass-based fakes** with `cast()` to satisfy the type checker — not `unittest.mock`.
- Example pattern: `_User`, `_Channel`, `_Attachment` dataclasses that stand in for discord types.
- `test_bot_utils.py` covers bot logic, permissions, message routing, attachment validation.
- `test_config.py` covers config masking and OpenAI config merging.
- `test_prompts.py` covers system prompt assembly.

## Docker

- `docker compose up` reads `config.yaml` as a read-only bind mount (`:ro`).
- Dockerfile installs from `requirements.txt` — this file must be generated from `uv` if using Docker.

## Slash commands

- `/model <name>` — switch LLM model (admin only per `permissions.users.admin_ids`). Autocomplete reloads config on empty input.
- `/abnt <doc> [instructions]` — evaluate `.docx`/`.odt` for ABNT compliance. Returns structured JSON then reformats into a user message.
- `/pesquisa` — web search + LLM document generation. Uses DuckDuckGo. Supports depth/audience/format options.
