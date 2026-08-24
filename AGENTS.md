# AGENTS.md

## Quick commands

```bash
# Linux/macOS (via uv)
uv run pytest                          # run all tests
uv run pytest tests/test_bot_utils.py  # run one file
uv run basedpyright src tests          # typecheck
uv run ruff check .                    # lint
uv run ruff format --check .           # check formatting
uv run python main.py                  # run the bot

# Windows (uv trampoline is broken — use .venv/Scripts/ directly)
.venv\Scripts\python.exe -m pytest     # run all tests
.venv\Scripts\python.exe -m pytest tests\test_bot_utils.py
.venv\Scripts\python.exe -m basedpyright src tests
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\python.exe main.py
```

- `main.py` → `src/main.py:run()` → `src/bot.py:create_discord_bot()` — this is the bot lifecycle.
- `main.py` in the repo root delegates to `src.main.run()` — both are valid entrypoints.
- `src/bot.py` owns the `on_message` handler, `MsgNode` cache, reply chains, LLM streaming, response splitting, and trigger-command routing. All slash commands are registered from there.

## Package layout

| Directory | Purpose |
|---|---|
| `src/bot.py` | Core bot: message routing, reply chains, LLM streaming, trigger commands |
| `src/config.py` | YAML config loading, OpenAI client factory, config masking |
| `src/commands/slashes/` | Slash commands: `/help`, `/model`, `/abnt`, `/pesquisa`, `/cronograma`, `/peca`, `/jurisprudencia`, `/relatorio`, `/regex`, `/sql`, `/json`, `/status-reset`, `/status-time` |
| `src/commands/triggers/` | Trigger commands: `lex!capture` (prefix-based, outside AI chat) |
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
- **All commands go through `uv run`** on Linux/macOS, or `.venv\Scripts\*.exe` on Windows. Never use a bare host `python` — it may not exist or be the wrong version. `uv` manages the isolated `.venv/`.
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

- `/help` — explica todos os comandos. **Sempre atualize `src/commands/slashes/help.py`** quando uma funcionalidade visível ao usuário for adicionada, removida ou alterada.
- `/model <name>` — switch LLM model (admin only per `permissions.users.admin_ids`). Autocomplete reloads config on empty input.
- `/abnt <doc> [instructions]` — evaluate `.docx`/`.odt` for ABNT compliance. Returns structured JSON then reformats into a user message.
- `/pesquisa` — web search + LLM document generation. Uses Tavily when `search.tavily.enabled` is true (`api_key` or `TAVILY_API_KEY` env var; empty key = rate-limited keyless mode); otherwise DuckDuckGo, which is also the fallback when Tavily fails. Supports depth/audience/format options.
- `/cronograma` — personalized study schedule with interactive weekday picker and multi-format export.
- `/peca <enunciado> [file] [tipo] [area]` — generate procedural legal documents.
- `/jurisprudencia <query> [corte] [file]` — search and summarize Brazilian case law.
- `/relatorio <titulo> <descricao>` — generate structured academic reports.
- `/regex <descricao>` — build and test regex from natural language description.
- `/sql <query>` — format and explain SQL queries.
- `/json <input>` — validate, format, minify, or convert JSON/YAML.
- `/status-reset` — force immediate status regeneration (admin only).
- `/status-time` — show time until next automatic status change.

## Trigger commands

- Prefix: `TRIGGER_PREFIX` constant in `src/helpers/ui.py` (default `"lex!"`).
- Commands live in `src/commands/triggers/`. Each registers via the `@trigger("name")` decorator from `__init__.py`.
- The bot's `on_message` handler checks for the prefix BEFORE any AI chat logic. If matched, the message is routed to the trigger handler and NOT processed by the LLM.
- Trigger handlers receive `(message, args, state, httpx_client)` where `args` is the text after the command name.
- Example: `lex!capture print("hello")` → `cmd_name="capture"`, `args='print("hello")'`.
