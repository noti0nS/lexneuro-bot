# PRD: `/pesquisa` — LexNeuro Academic & Legal Document Generator

## Overview

### Purpose
Enable law students, legal professionals, and developers to generate structured documents — academic papers, legal pieces, and technical documentation — from fragmentary instructions. The bot infers intent from dropdown selections and a short topic string, eliminating the need for long free-text prompts. Web search runs autonomously via LLM tool calling.

### Target Users
Brazilian law students (NPJ assignments), practicing lawyers (peças processuais), and programmers using the Neuro persona for technical documentation.

---

## User Flow

```
1. User invokes /pesquisa tema="competência FGTS falecimento"
   contexto=NPJ extensao=padrao páginas=5 modo_pensamento=True
   instrucoes_extras="3 peças: inicial, contestação, reconvenção"
2. Bot responds ephemeral: "Pesquisando e gerando o documento..."
3. LLM performs self-Q&A refinement: asks itself 3-5 clarifying questions
   about the topic, answers them from its own knowledge (~5-10s)
4. Refinement output is appended as context to the conversation
5. LLM performs web searches autonomously (DuckDuckGo), fetches pages,
   generates final document in LexNeuro persona
6. Bot sends DOCX/ODT file attachment (or threaded messages if large)
```

---

## Slash Command Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `tema` | STRING | Yes | — | Main topic in free text. Ex: "alvará judicial no TJSP aprofundado" |
| `contexto` | STRING (Choice) | No | `academico` | Document type / persona. Values: `academico` (`🎓 Acadêmico / ABNT`), `npj` (`⚖️ NPJ / Peça Jurídica`), `programacao` (`💻 Programação / Neuro`) |
| `extensao` | STRING (Choice) | No | `padrao` | Depth preset. Values: `curto` (Direto ao Ponto ~1 pág. / 500w), `padrao` (Padrão ~3 págs. / 1500w), `completo` (Dossiê Completo 5+ págs. / 2500+w) |
| `páginas` | INTEGER | No | `3` | Target page count (1–50). Works alongside `extensao` — when both are provided, the explicit page count takes precedence. |
| `modo_pensamento` | BOOLEAN | No | `False` | Switches to reasoning model (configurable via `research.thinking_model`) |
| `instrucoes_extras` | STRING | No | — | Free-text fragmentary instructions. Ex: "3 peças: inicial, contestação, reconvenção" |
| `format` | STRING (Choice) | No | `docx` | Output file format. Values: `docx`, `odt` |

---

## Core Feature Specifications

### LexNeuro System Prompt

Dynamic f-string template in `src/prompts/pesquisa.py`. All user-selected params are interpolated into the system prompt. ABNT reference guide (from `src/prompts/abnt.py:load_abnt_reference()`) and web search tool descriptions are appended.

```
Você é o LexNeuro, um assistente jurídico e acadêmico de elite.
Sua missão é inferir a intenção do usuário a partir de instruções fragmentadas e produzir um documento final perfeitamente estruturado, sem exigir explicações adicionais.

### PARÂMETROS DA SOLICITAÇÃO:
- Tema Central: {tema}
- Contexto: {contexto} (Se for "NPJ / Peça Jurídica", atue como um advogado sênior elaborando peças estruturadas, endereçamentos e jurisprudência aplicável).
- Extensão Desejada: {extensao} (Adeque o nível de detalhe para atingir essa proporção aproximada de texto).
- Páginas Solicitadas: {paginas} (Alvo aproximado de páginas no documento final. Priorize este número sobre a extensão se houver conflito).
- Modo de Pensamento Ativo: {modo_pensamento} (Se True, explore teses minoritárias e debates profundos).
- Diretrizes Extras: {instrucoes_extras}

### REGRAS DE EXECUÇÃO:
1. COMPREENSÃO DE FRAGMENTOS: Se pedido "3 peças", não explique o que são. Escreva imediatamente o esqueleto estrutural das 3 peças com base no tema.
2. MARKDOWN DISCORD: Use `#` para grandes divisões e `**` para destacar artigos de lei (ex: **Art. 319 do CPC**). Use `>` para simular recuos de citação direta longa (ABNT).
3. RIGOR (LEX): Nunca invente jurisprudência. Indique competência correta e fundamentação real. Se houver divergência, exponha ambas as correntes.
4. TOM: Direto, culto e resolutivo. Vá direto ao documento final.

### FERRAMENTAS DE PESQUISA:
Você tem acesso a `web_search` (busca DuckDuckGo por artigos, jurisprudência, doutrina) e `fetch_page` (conteúdo integral de URLs). Use múltiplas buscas com diferentes ângulos. Reúna fontes antes de redigir. Priorize fontes confiáveis: doutrina, jurisprudência oficial, artigos acadêmicos.

### FORMATAÇÃO:
- Use notas de rodapé numeradas (¹, ²) com citações ABNT.
- Inclua "REFERÊNCIAS" ao final em ABNT NBR 6023.
- Produza APENAS o conteúdo do documento — sem comentários fora do documento.
```

### Extensão & Páginas Interaction

Both params are injected into the prompt. When `páginas` differs from the extensão preset's implied page count, `páginas` takes precedence. The LLM receives both and is instructed to prioritize the explicit number.

Example: `extensao=curto` (~1 page) + `páginas=5` → LLM targets ~5 pages but uses the "curto" verbosity style (concise paragraphs, minimal elaboration).

### Pre-Generation Refinement (Self-Q&A)

Before the tool-calling loop begins, the bot makes a single non-streaming call to the LLM with `tool_choice="none"`. This call prompts the model to formulate and answer its own clarifying questions about the topic, producing an **Análise Preliminar** block. The output is appended as an assistant message to the conversation history, giving the subsequent research loop richer context.

**Purpose:** The user provides fragmentary input (a short topic string + dropdown choices). The LLM fills gaps by reasoning about what a specialist would ask — jurisdiction, applicable law, time period, doctrinal schools, procedural posture — and answering from its training knowledge. This produces more precise web searches and a better-structured final document.

**Refinement prompt:**
```
Antes de iniciar a pesquisa, reflita sobre o tema. Formule de 3 a 5
perguntas esclarecedoras que um especialista faria e responda cada uma
com seu melhor conhecimento jurídico. Seja conciso. Não faça buscas —
apenas raciocine.

Formato:
### ANÁLISE PRELIMINAR
**Pergunta 1:** [pergunta]
**Resposta:** [resposta]

**Pergunta 2:** [pergunta]
**Resposta:** [resposta]

...

Ao final, prossiga com a pesquisa web e a redação do documento.
```

**Flow:**
```
build_pesquisa_messages() → messages[]
  │
  ├─ 1. Refinement call (tool_choice="none")
  │     openai_client.chat.completions.create(...)
  │     raw = get_completion_text(...)
  │
  ├─ 2. Append: messages.append({"role": "assistant", "content": raw})
  │
  ├─ 3. Normal tool-calling loop (web_search, fetch_page, generate)
  │
  └─ 4. File generation + delivery
```

**Gating:** Controlled by config key `research.refinement_enabled` (default `true`). When `false`, the refinement call is skipped and the tool loop starts immediately (same as v1 behavior).

**Model:** The refinement call uses the same model as the main loop (respecting `modo_pensamento` routing). No separate model configuration needed.

### Web Search via LLM Tool Calling

- A `web_search(query)` function tool is registered with the LLM via OpenAI's native function calling API.
- The LLM decides **when** to search and **what** to search for. No upfront search is performed.
- Each tool call executes a DuckDuckGo search and returns structured results (title, url, snippet) injected back into the conversation as tool response messages.
- A `fetch_page(url)` tool lets the LLM retrieve full content of promising pages.
- Loop has a configurable maximum iteration limit (`max_tool_iterations`, default 15).
- If the loop exhausts, a final call is forced with `tool_choice="none"`.

### Thinking Model Routing

| Condition | Model Used |
|-----------|-----------|
| `modo_pensamento=False` | `state.curr_model` (global, set via `/model`) |
| `modo_pensamento=True` + config has `research.thinking_model` | Config value (e.g. `deepseek/deepseek-r1`) |
| `modo_pensamento=True` + no config key | Falls back to `state.curr_model` |

DeepSeek `reasoning_content` is handled by existing `_needs_deepseek_reasoning()` in `src/config.py` — empty `reasoning_content` is injected into assistant messages before API calls. `get_completion_text()` extracts only `content`, not reasoning, so reasoning is naturally excluded from the final output and message history.

### File Output & Delivery

- Generate `.docx` via `python-docx` + pandoc, ABNT margins applied.
- Generate `.odt` via `odfpy` + pandoc.
- Filename format: `pesquisa_[title_slug]_[timestamp].[ext]`
- Delivery strategy:

| Condition | Action |
|-----------|--------|
| File size < 8MB | Send as Discord file attachment |
| File size > 8MB | Create new thread in channel, send chunked messages |

### LLM Call Pattern

Two-phase non-streaming with `await_task_with_heartbeats`:

**Phase 1 — Refinement (if `research.refinement_enabled` is `true`):**
- Single call to the LLM with `tool_choice="none"` and the refinement prompt
- Output is appended as an assistant message to `messages[]`

**Phase 2 — Research & Generation:**
- Messages include system prompt, refinement output (assistant), and user topic
- Tool-calling loop sends messages to the LLM and processes responses:
  - `finish_reason == "stop"` with content → document complete, exit loop
  - `finish_reason == "tool_calls"` → execute searches, append results, continue loop
  - `finish_reason == "length"` → capture content, exit loop
  - `finish_reason == "content_filter"` → error to user
- If the loop exhausts `max_tool_iterations`, force final call with `tool_choice="none"`

---

## Configuration

```yaml
# config-example.yaml additions
research:
  max_tool_iterations: 15
  search_results_per_topic: 8
  max_page_fetches: 5
  thinking_model: deepseek/deepseek-r1
  refinement_enabled: true
```

| Key | Default | Purpose |
|-----|---------|---------|
| `research.max_tool_iterations` | `15` | Max web search loop iterations |
| `research.search_results_per_topic` | `8` | Results per DuckDuckGo topic search |
| `research.max_page_fetches` | `5` | Max pages fetched via `fetch_page` tool |
| `research.thinking_model` | `deepseek/deepseek-r1` | Model used when `modo_pensamento=True`. Format: `provider/model` |
| `research.refinement_enabled` | `true` | Whether to run the pre-generation self-Q&A refinement call before the tool loop |

Config is hot-reloaded on every invocation via `await asyncio.to_thread(get_config)`. No caching.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/commands/pesquisa.py` | **Edit** — new parameters (`tema`, `contexto`, `extensao`, `páginas`, `modo_pensamento`, `instrucoes_extras`), thinking model routing, pre-generation refinement call, updated `build_pesquisa_messages()` call |
| `src/prompts/pesquisa.py` | **Edit** — LexNeuro dynamic system prompt, refinement prompt, updated function signature with all 6 interpolation variables |
| `config-example.yaml` | **Edit** — add `research.thinking_model`, `research.refinement_enabled` |
| `tests/test_pesquisa.py` | **Create** — unit tests for prompt building, model routing, parameter validation |

---

## Edge Cases & Error Handling

| Case | Behavior |
|------|----------|
| Empty `tema` | Ephemeral: "Descreva sua pesquisa." |
| `páginas` < 1 | Ephemeral: "O número de páginas deve ser no mínimo 1." |
| `páginas` > 50 | Ephemeral: "O número de páginas não pode exceder 50." |
| `contexto` omitted | Default `academico` |
| `extensao` omitted | Default `padrao` |
| `modo_pensamento=True` but no `thinking_model` config | Fallback to `state.curr_model`, log warning |
| Refinement call fails (APIError) | Log warning, skip refinement, proceed directly to tool loop |
| Refinement call returns empty output | Log warning, skip refinement append, proceed to tool loop |
| `refinement_enabled=false` | Skip refinement entirely, start tool loop immediately |
| LLM returns document without searching | Accept and proceed (valid path) |
| LLM calls `web_search` with empty query | Return empty results in tool response; LLM may retry |
| Search returns no results | Return `[]` in tool response; LLM may retry or use training knowledge |
| Search throws exception | Return error string in tool response; LLM may retry |
| `fetch_page` fails | Return error string; LLM may try another URL |
| `fetch_page` exceeds `max_page_fetches` limit | Return limit message; LLM continues with available sources |
| Tool loop exceeds `max_tool_iterations` | Force final call with `tool_choice="none"` |
| LLM returns `finish_reason="length"` | Capture partial content, exit loop |
| LLM returns `finish_reason="content_filter"` | Ephemeral error to user |
| Provider error (APIError) | `followup.send()` with provider detail |
| File > 8MB | Thread delivery with chunked messages |
| `generate_document` fails | Send raw text in messages instead |

---

## Example Interaction

```
User:
  /pesquisa tema="competência FGTS falecimento"
            contexto="⚖️ NPJ / Peça Jurídica"
            extensao="Padrão (~3 págs. / 1500w)"
            páginas=5
            modo_pensamento=True
            instrucoes_extras="3 peças: inicial, contestação, reconvenção"

Bot (ephemeral):
  Pesquisando e gerando o documento... Isso pode levar alguns minutos.

  [LLM performs self-Q&A refinement, asking and answering 4 clarifying
   questions about FGTS competency, succession law, applicable CPC articles,
   and jurisprudential divisions. Refinement output is saved as context.]

  [LLM then searches web for FGTS jurisprudence, fetches relevant pages,
   switches to DeepSeek-R1 for deep reasoning, generates 5-page document
   with 3 structured legal pieces informed by the refinement context]

Bot (followup):
  Pesquisa concluída! Aqui está o documento:
  📎 pesquisa_competencia_FGTS_falecimento_20260505_143022.docx
```

---

## Testing

Test file: `tests/test_pesquisa.py`

- `test_build_messages_defaults` — only tema, all defaults interpolated
- `test_build_messages_all_params` — all 6 params injected into prompt
- `test_build_messages_paginas_in_prompt` — páginas value appears in system prompt
- `test_build_messages_npj_context` — NPJ context injects "advogado sênior" guidance
- `test_build_messages_programacao_context` — Programação context present in prompt
- `test_build_messages_extensao_curto` — extensao=curto reflects ~500w constraint
- `test_build_messages_extensao_completo` — extensao=completo reflects 2500+w constraint
- `test_build_messages_modo_pensamento_true` — modo_pensamento=True appears in prompt
- `test_build_messages_instrucoes_extras` — instrucoes_extras injected verbatim
- `test_build_messages_includes_abnt_reference` — ABNT reference appended to system prompt
- `test_build_messages_returns_list_of_dicts` — output is `list[dict]` with role/content keys
- `test_empty_tema_rejected` — empty string → validation error
- `test_contexto_choices_count` — exactly 3 choices
- `test_extensao_choices_count` — exactly 3 choices
- `test_format_choices_count` — exactly 2 choices
- `test_build_pesquisa_filename` — filename sanitization + timestamp pattern
- `test_thinking_model_routing` — modo_pensamento=True routes to thinking_model from config
- `test_thinking_model_fallback` — missing config key falls back to state.curr_model
- `test_refinement_prompt_built` — refinement prompt contains "ANÁLISE PRELIMINAR" and expects 3-5 questions
- `test_refinement_disabled` — refinement_enabled=false skips the self-Q&A call
- `test_refinement_output_appended` — refinement result appears as assistant message in messages[]

Fakes follow existing pattern from `tests/test_bot_utils.py` (dataclass-based with `cast()`).

---

## Out of Scope & Future Enhancements

### Out of Scope (v1)
- User-provided attachments as sources
- Citation database / reference manager integration
- Pagination enforcement via token counting (LLM estimates page count; no hard cutoff)
- PDF output format
- Streaming generation
- Follow-up refinement messages ("add more Civil references")
- Multiple provider fallback for thinking model

### Future Enhancements
- PDF output format
- Hard page count enforcement via token/character budgeting
- `/pesquisa` refinement via follow-up messages
- Multiple thinking model fallback chain
- Citation style customization (ABNT alternatives)
- Web search provider swapping (beyond DuckDuckGo)
