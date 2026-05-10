<p align="center">
  <img src="assets/lexneuro_banner.png" alt="LexNeuro Banner">
</p>

<h1 align="center">LexNeuro</h1>

<h3 align="center"><i>
  Legal, academic, programming, and technical Discord assistant
</i></h3>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13+-blue?logo=python&logoColor=white" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/code%20style-ruff-261230?logo=ruff&logoColor=white" alt="Ruff">
  <img src="https://img.shields.io/badge/type%20checked-basedpyright-2c3e50" alt="basedpyright">
</p>

---

LexNeuro is a Discord bot that turns your server into an AI-powered study and coding assistant. It supports academic research with web search, ABNT compliance evaluation, programming help, personalized study schedules, and context-aware conversations via reply chains — all powered by LLM models of your choice. More commands are on the way.

---

## Commands

### `/pesquisa` — Academic document generation
Produces articles, legal briefs, or technical documentation with integrated web search (DuckDuckGo). The model runs an agentic loop of searching and reading pages before writing.

Three contexts: **Academic / ABNT**, **NPJ / Legal Brief**, **Programming / Neuro**. Three length levels: short (~1 page), standard (~3 pages), full (5+ pages). Exports to `.docx` and `.odt`.

### `/abnt` — ABNT compliance evaluation
Upload a `.docx` or `.odt` file and receive a score (0–1) with a list of structural improvements per ABNT standards. Accepts optional instructions to focus the evaluation.

### `/cronograma` — Personalized study schedule
Set the exam date and subjects. The bot shows an interactive weekday picker, calculates available study days, and generates a schedule exportable as PDF, Markdown, DOCX, or ODT.

### `/model` — Model switching
Admins can switch between configured LLM models without restarting the bot. Autocomplete loads models from `config.yaml` in real time.

---

## Context-aware chat

The bot understands **reply chains**: reply to the bot's own message to continue the conversation with full context. Consecutive messages from the same author are automatically chained. Just mention the bot (`@LexNeuro`) to start or branch a conversation.

Supports:
- Image attachments (vision models)
- Text files (`.txt`, `.py`, `.c`, etc.)
- Streamed responses with automatic long-message splitting
- Discord threads for parallel conversations

---

## Supported providers

Any OpenAI-compatible API:

| Provider | Example |
|---|---|
| OpenAI | `openai/gpt-5` |
| OpenRouter | `openrouter/claude-4` |
| Groq | `groq/llama-4` |
| DeepSeek | `deepseek/deepseek-chat` |
| Google Gemini | `gemini/gemini-2.5-pro` |
| xAI | `xai/grok-4` |
| Mistral | `mistral/mistral-large` |
| Ollama (local) | `ollama/llama4` |
| LM Studio (local) | `lm-studio/qwen-3` |
| vLLM (local) | `vllm/deepseek-r1` |

---

## Setup

### 1. Discord Developer Portal

You must create a bot application before running the bot:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. In **Bot** settings, click **Reset Token** (or **Copy**) to get your **bot token**. Paste it into `config.yaml` as `bot_token`.
3. Copy the **Application ID** (under **General Information**) into `config.yaml` as `client_id`.
4. Under **Bot > Privileged Gateway Intents**, enable **Message Content Intent** and save. This is required for the bot to read chat messages.
5. Use the **OAuth2 > URL Generator** to invite the bot to your server:
   - **Scopes**: `bot`, `applications.commands`
   - **Bot Permissions**: `Send Messages`, `Read Messages`, `Read Message History`, `Use Slash Commands`, `Attach Files`, `Add Reactions`

   Alternatively, the bot prints a ready-to-use invite URL on startup when `client_id` is set.

Refer to the [Discord developer docs](https://discord.com/developers/docs/quick-start/getting-started) for detailed guidance.

### 2. Configuration

You need two config files — both are gitignored and have commented example templates:

```bash
cp config-example.yaml config.yaml
cp litellm_config-example.yaml litellm_config.yaml
```

**`config.yaml`** — bot settings, permissions, LLM providers & models:

- `bot_token` / `client_id` — from step 1 above.
- `providers` — API endpoints and keys for each provider (OpenAI, Groq, OpenRouter, etc.). Leave unused providers empty.
- `models` — the models available via `/model`, formatted as `provider/model`. The first model listed is the default.
- `permissions` — restrict bot access by user ID, role ID, or channel ID.
- `abnt`, `cronograma`, `research` — command-specific tuning knobs.
- `system_prompt` — overwrite the default personality; `{date}` and `{time}` are replaced at runtime.

**`litellm_config.yaml`** (Docker only) — the [LiteLLM proxy](https://docs.litellm.ai/) config. Defines model aliases, load-balancing, and fallbacks. The example template includes a wildcard passthrough so all `config.yaml` models work out of the box.

**Environment variable overrides** — any provider key can be set via env vars instead of writing it in the YAML:

```
PROVIDER_OPENAI_API_KEY=sk-...
PROVIDER_GROQ_API_KEY=gsk-...
PROVIDER_OPENAI_BASE_URL=https://api.openai.com/v1
```

The pattern is `PROVIDER_{PROVIDER}_API_KEY` and `PROVIDER_{PROVIDER}_BASE_URL` (provider name is uppercased). This is useful for cloud deployments where committing API keys is undesirable.

### 3a. Run with Docker (recommended)

```bash
docker compose up
```

This starts two services:
- **`bot`** — the LexNeuro bot, reading `config.yaml` via a read-only bind mount.
- **`litellm`** — a LiteLLM proxy sidecar that handles auth, rate limits, load-balancing, and fallbacks across all your providers.

The bot communicates with LiteLLM under the `litellm/` provider prefix. You can still use direct providers (e.g. `openai/gpt-5`) — the wildcard passthrough in `litellm_config.yaml` relays them unchanged.

*Note: the Dockerfile installs `pandoc` and `texlive` for `.docx`/`.odt`/`.pdf` export. The image is heavy (~1.5 GB). If you don't need document export you can slim it down.*

### 3b. Run without Docker

**Requirements:** [Python 3.13+](https://python.org) and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Run
uv run python main.py
```

Without Docker there is no LiteLLM sidecar — configure providers directly in `config.yaml` (the `litellm_config.yaml` file is unused) and supply API keys via the provider config or environment variables.

**Optional: document export support** — `/pesquisa` exports `.docx` and `.odt`; `/cronograma` exports `.pdf`. These depend on `pandoc` and `texlive` being installed on the host machine. Install them via your system package manager if you need these features.

### 4. Verify

Check the logs on startup. You should see the masked config dump and the bot invite URL. Once the bot is online, try `/model` in any channel the bot can see.

---

## Project structure

| Directory | Purpose |
|---|---|
| `src/` | Core bot code |
| `src/commands/` | Slash commands (`/pesquisa`, `/abnt`, `/cronograma`, `/model`) |
| `src/helpers/` | Utilities: LLM streaming, web search, document I/O, UI, status |
| `src/prompts/` | System prompts and formatting references |
| `tests/` | Automated tests |
| `assets/` | Images and visual assets |

---

## Development

```bash
uv run pytest                  # tests
uv run basedpyright src tests  # type checking
uv run ruff check .            # lint
uv run ruff format --check .   # formatting
```

---

## License

This project began as a fork of [llmcord](https://github.com/jakobdylanc/llmcord) by [jakobdylanc](https://github.com/jakobdylanc). Original portions are licensed under the MIT License (see `LICENSE-ORIGINAL`), while all subsequent modifications are licensed under Apache 2.0 (see `LICENSE`).
