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

1. Clone the repo:

```bash
git clone https://github.com/noti0nS/lexneuro-bot
cd lexneuro-bot
```

2. Copy and configure:

```bash
cp config-example.yaml config.yaml
```

Fill in `bot_token`, `client_id`, providers, and models. The file is fully commented.

3. Run with Docker:

```bash
docker compose up
```

Or without Docker (requires Python 3.13+ and `uv`):

```bash
uv run python main.py
```

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
