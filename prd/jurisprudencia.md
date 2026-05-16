# PRD: `/jurisprudencia` — Pesquisa de Jurisprudência

## Overview

### Purpose
Search and summarize Brazilian judicial precedents from public court websites (STF, STJ, TST, etc.) via web search with LLM tool calling. The bot uses DuckDuckGo + `fetch_page` to find relevant decisions, then produces a structured research document with proper legal citations.

### Target Users
Brazilian law students, legal professionals, and researchers who need to quickly find and summarize relevant court decisions (jurisprudência) on a legal topic.

---

## User Flow

```
1. User invokes /jurisprudencia consulta="prescrição intercorrente
   na execução fiscal" tribunal=stj formato=texto
2. Bot responds ephemeral: "Buscando jurisprudência..."
3. LLM searches the web autonomously (web_search targeting STF/STJ
   sites, fetch_page for full decision text), then generates a
   structured summary of relevant decisions
4. Bot sends the result as a followup message (or file if DOCX)
```

---

## Slash Command Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `consulta` | STRING | Yes | — | Free-text topic description. e.g. "responsabilidade civil do Estado por omissão" |
| `tribunal` | STRING (Choice) | No | `todos` | Court filter. See choices table below. |
| `periodo` | STRING | No | — | Date range constraint. e.g. "2023-2024", "últimos 2 anos", "após 2020". Free-text for flexibility. |
| `formato` | STRING (Choice) | No | `texto` | Output format: `texto` (Discord message) or `docx` (Word document attachment). |

**Tribunal choices:**

| Label | Value |
|---|---|
| `Todos os tribunais` | `todos` |
| `STF — Supremo Tribunal Federal` | `stf` |
| `STJ — Superior Tribunal de Justiça` | `stj` |
| `TST — Tribunal Superior do Trabalho` | `tst` |
| `TJDFT — Tribunal de Justiça do DF` | `tjdft` |
| `TJSP — Tribunal de Justiça de SP` | `tjsp` |
| `TRF-1 — 1ª Região` | `trf1` |
| `TRF-2 — 2ª Região` | `trf2` |
| `TRF-3 — 3ª Região` | `trf3` |
| `TRF-4 — 4ª Região` | `trf4` |
| `TRF-5 — 5ª Região` | `trf5` |

Excluded from v1: TSE, STM, TJMG, TJRJ — the 11 choices above cover the highest-volume research targets and fit within Discord's 25-option limit.

**Formato choices:**

| Label | Value |
|---|---|
| `Texto (mensagem)` | `texto` |
| `DOCX (arquivo Word)` | `docx` |

---

## Core Feature Specifications

### Web Search Strategy

The LLM is given `web_search` and `fetch_page` as function-calling tools (identical to the tool schemas used in `pesquisa.py`). The system prompt directs the LLM to:

- Target official court portals: `portal.stf.jus.br`, `stj.jus.br`, `tst.jus.br`, and state/regional court portals.
- Include `site:` qualifiers in DuckDuckGo queries for domain-restricted searches.
- Supplement with legal news sites (`jusbrasil.com.br`, `migalhas.com.br`, `conjur.com.br`) when official sources are insufficient.
- Use varied query phrasings: include terms like "jurisprudência", "acórdão", "ementa", "recurso repetitivo", "repercussão geral".
- Fetch the full text of the most promising results via `fetch_page` before summarizing.

The tool loop is capped by `jurisprudencia.max_search_iterations` (default 12). Each `web_search` call returns up to `jurisprudencia.search_results_per_query` (default 8) results. `fetch_page` calls are capped at `jurisprudencia.max_page_fetches` (default 5) total.

### LLM Prompt Design

Prompt built in `src/prompts/jurisprudencia.py` following the `pesquisa.py` pattern.

#### System Prompt

```text
Você é um pesquisador jurídico brasileiro especializado em jurisprudência.
Sua função é buscar, selecionar e sumarizar decisões judiciais relevantes
dos tribunais brasileiros.

### FERRAMENTAS DISPONÍVEIS:
- `web_search(query)`: busca DuckDuckGo. Use múltiplas buscas com diferentes
  ângulos. Inclua termos como "jurisprudência", "acórdão", "ementa",
  "recurso repetitivo", "repercussão geral" nas queries.
- `fetch_page(url)`: obtém o texto integral de uma página (até 8.000 chars).
  Use para ler o teor completo das decisões mais promissoras.

### ESTRATÉGIA DE BUSCA:
- Direcione buscas para os sites oficiais dos tribunais:
  - STF: portal.stf.jus.br
  - STJ: stj.jus.br
  - TST: tst.jus.br
  - Use `site:` nos termos de busca quando relevante.
- Complemente com sites jurídicos: jusbrasil.com.br, migalhas.com.br,
  conjur.com.br.
- Reúna fontes antes de redigir. Não cite uma decisão sem antes buscar
  seu texto integral ou ementa.

### FORMATAÇÃO DA RESPOSTA:
Para cada decisão relevante encontrada, apresente:
- Número do processo (RE, REsp, AgInt, RMS, HC, etc.)
- Tribunal e órgão julgador
- Relator(a)
- Data do julgamento
- Ementa ou resumo do entendimento
- Tese fixada (se houver — recursos repetitivos, repercussão geral,
  súmulas vinculantes)

Agrupe os resultados por tribunal (se múltiplos) ou por relevância.
Destaque:
- Teses de repercussão geral e recursos repetitivos
- Súmulas vinculantes aplicáveis
- Divergências entre tribunais, se existirem

### REGRAS:
1. NUNCA invente jurisprudência, números de processo, ementas ou relatores.
   Se não encontrar resultados relevantes, informe honestamente.
2. Use markdown do Discord para formatar (negrito para números de processo,
   listas, blocos de código para ementas longas).
3. Inclua ao final uma seção "CONCLUSÃO" com o entendimento predominante.
4. Se houver teses conflitantes entre tribunais, apresente ambas as
   correntes com suas respectivas decisões.

Responda APENAS com a pesquisa de jurisprudência — sem introduções, sem
"claro!", sem comentários fora do documento.
```

#### User Message (constructed dynamically)

```text
Tema da consulta: {consulta}
Tribunal(is): {tribunal_label}
Período: {periodo or "sem restrição"}

Busque jurisprudência sobre o tema acima e produza uma pesquisa estruturada
com as decisões mais relevantes encontradas. Priorize decisões recentes e
de tribunais superiores.
```

The `tribunal_label` is resolved from a `TRIBUNAL_LABELS` dict in the prompts module (e.g., `stf` → `STF — Supremo Tribunal Federal`). When `tribunal=todos`, the label is `Todos os tribunais`.

### LLM Call Pattern

Follow the `pesquisa.py` pattern exactly (non-streaming completions with tool-calling loop and `await_task_with_heartbeats`):

1. **Permission check**: if `register_jurisprudencia_command` receives `user_has_permission`, check before proceeding.
2. **Acknowledge**: `await interaction.response.send_message("Buscando jurisprudência...", ephemeral=True)`.
3. **Read config**: `jur_config = state.config.get("jurisprudencia", {})`.
4. **Build messages**: `messages = build_jurisprudencia_messages(consulta, tribunal, periodo)`.
5. **Get LLM client**: `openai_client, openai_config = get_openai_config(state.config, state.curr_model)`.
6. **Tool-calling loop** (`for iteration in range(max_iterations)`):
   - Call `openai_client.chat.completions.create(**build_openai_chat_completion_kwargs(openai_config, messages, stream=False, tools=JURISPRUDENCIA_TOOLS, tool_choice="auto"))`.
   - Wrap in `await_task_with_heartbeats(completion_task, "jurisprudencia")`.
   - Extract `raw_output = get_completion_text(completion)`.
   - `finish_reason == "stop"` + content → exit loop.
   - `finish_reason == "tool_calls"` → execute `web_search` / `fetch_page`, append results as tool messages, continue.
   - `finish_reason == "length"` → capture partial content, exit.
   - `finish_reason == "content_filter"` → ephemeral error.
   - If loop exhausts → force final call with `tool_choice="none"`.
7. **Output**:
   - `formato == "texto"` → `sanitize_discord_markdown(raw_output)` → send via `interaction.followup.send()`, splitting at 2000 chars if needed.
   - `formato == "docx"` → `generate_document(raw_output, formato="docx")` → `send_document_result(...)`.
8. **Error handling**: `APIError` → `followup.send()` with provider detail. General `Exception` → log + ephemeral error.

Why non-streaming: the output is a structured research document. Streaming adds complexity for marginal UX benefit. Follow the established non-streaming pattern.

### Tool Definitions

Reuse the tool schemas from `ALL_PESQUISA_TOOLS` in `pesquisa.py` — same `web_search` and `fetch_page` functions with identical JSON schemas:

```python
JURISPRUDENCIA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Busca na web via DuckDuckGo. Retorna título, URL e snippet para cada resultado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termos de busca"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Obtém o texto completo de uma página web (até 8.000 caracteres).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL da página a ser carregada"}
                },
                "required": ["url"],
            },
        },
    },
]
```

### Output Format Details

**`texto` (Discord message):**
- Apply `sanitize_discord_markdown()` to strip unsupported markdown.
- If content ≤ 2000 chars: single `interaction.followup.send(content=...)`.
- If content > 2000 chars: split at paragraph boundaries (`\n\n`), send sequential followup messages.

**`docx` (Word file):**
- `generate_document(raw_output, formato="docx")` from `src/helpers/documents.py`.
- `send_document_result(interaction, content, filename, file_bytes, label="Jurisprudência")` from `src/helpers/send.py`.
- Filename: `jurisprudencia_[slug]_[timestamp].docx` where slug = first 40 chars of `consulta`, sanitized (lowercase, spaces → underscore, strip non-alphanumeric).
- If file > 8MB: `send_document_result` falls back to thread delivery with chunked text.

---

## Configuration

```yaml
# config-example.yaml additions
jurisprudencia:
  max_search_iterations: 12
  search_results_per_query: 8
  max_page_fetches: 5
```

| Key | Default | Purpose |
|---|---|---|
| `jurisprudencia.max_search_iterations` | `12` | Max tool-calling loop iterations |
| `jurisprudencia.search_results_per_query` | `8` | Results per DuckDuckGo search query |
| `jurisprudencia.max_page_fetches` | `5` | Max pages fetched via `fetch_page` tool |

Config is hot-reloaded on every invocation via `await asyncio.to_thread(get_config)`. No caching.

---

## Files to Create/Modify

| File | Action |
|---|---|
| `src/commands/jurisprudencia.py` | **Create** — slash command registration, tool-calling loop, LLM orchestration, output delivery |
| `src/prompts/jurisprudencia.py` | **Create** — `build_jurisprudencia_messages()`, `JURISPRUDENCIA_SYSTEM_PROMPT`, `TRIBUNAL_LABELS`, `JURISPRUDENCIA_TOOLS` |
| `src/prompts/__init__.py` | **Edit** — add export for `build_jurisprudencia_messages`, `TRIBUNAL_LABELS` |
| `src/helpers/ui.py` | **Edit** — add `TRIBUNAL_CHOICES` and `FORMATO_JURISPRUDENCIA_CHOICES` constants |
| `src/bot.py` | **Edit** — import and call `register_jurisprudencia_command(discord_bot, state, user_has_permission)` |
| `config-example.yaml` | **Edit** — add `jurisprudencia` section |
| `pyproject.toml` | (no change — no new dependencies) |

---

## Edge Cases & Error Handling

| Case | Behavior |
|---|---|
| Empty `consulta` | Ephemeral: "Descreva o tema da pesquisa de jurisprudência." |
| `consulta` < 5 characters | Ephemeral: "Descreva melhor o tema da pesquisa (mínimo 5 caracteres)." |
| `tribunal` is invalid | Handled by Discord — only valid choices appear in the dropdown |
| `periodo` is nonsensical (e.g. "banana") | Pass through to LLM as-is; LLM interprets best-effort or ignores |
| `formato` is invalid | Handled by Discord — only valid choices appear in the dropdown |
| No jurisprudence found (LLM output is empty or generic) | Followup: "Não foi possível encontrar jurisprudência relevante sobre o tema. Tente refinar a consulta ou ampliar o período." |
| LLM hallucinates cases | System prompt instructs against fabrication. No runtime hallucination detection in v1 — user should critically evaluate output. |
| `web_search` returns no results for a query | Return `[]` in tool response; LLM retries with different query |
| `web_search` throws exception | Return error string in tool response (`f"Search failed: {e}"`); LLM retries |
| `fetch_page` fails (timeout, 403, connection error) | Return error string in tool response; LLM tries another URL |
| `fetch_page` returns HTML but no meaningful text | Empty string returned; LLM moves to next source |
| `fetch_page` exceeds `max_page_fetches` limit | Return limit message: "Limite de páginas atingido"; LLM continues with available sources |
| Tool loop exceeds `max_search_iterations` | Force final call with `tool_choice="none"`, capture partial output |
| LLM returns `finish_reason="content_filter"` | Ephemeral: "O conteúdo gerado foi bloqueado pelo filtro de segurança. Tente reformular a consulta." |
| LLM returns `finish_reason="length"` | Capture partial content, exit loop, send what we have (max_tokens reached) |
| LLM returns `finish_reason="stop"` but empty content | Ephemeral: "Não foi possível gerar a pesquisa de jurisprudência." |
| Provider error (`APIError`) | `interaction.followup.send(f"Erro no provedor LLM: {detail}")` using `get_provider_error_detail()` |
| General exception in command handler | `logging.exception(...)` + `interaction.followup.send("Erro interno. Tente novamente.")` |
| Result > 2000 chars (texto format) | Split at `\n\n` paragraph boundaries into sequential followup messages |
| Result > 2000 chars but no paragraph breaks | Split at 1900 char boundary with `...` continuation indicator |
| File > 8MB (docx format) | `send_document_result` falls back to thread delivery with chunked text content |
| `generate_document` fails | Send raw text in followup messages as fallback |
| User doesn't have permission | `user_has_permission(...)` check → ephemeral rejection message |

---

## Example Interaction

```
User:
  /jurisprudencia consulta="prescrição intercorrente na execução fiscal"
  tribunal=stj periodo="últimos 5 anos" formato=texto

Bot (ephemeral):
  Buscando jurisprudência... Isso pode levar alguns minutos.

  [LLM searches via DuckDuckGo:
   "prescrição intercorrente execução fiscal STJ site:stj.jus.br",
   "REsp repetitivo prescrição intercorrente STJ",
   "tema repetitivo prescrição intercorrente execução fiscal",
   fetches 3 pages from STJ portal for full decision texts]

Bot (followup):
  # Pesquisa de Jurisprudência

  **Tema:** Prescrição intercorrente na execução fiscal
  **Tribunal:** STJ — Superior Tribunal de Justiça
  **Período:** últimos 5 anos

  ---

  ## REsp 1.340.553/RS (Tema 566 — Recurso Repetitivo)

  - **Relator:** Min. Mauro Campbell Marques
  - **Julgamento:** 12/06/2018
  - **Órgão:** 1ª Seção

  **Tese fixada (Tema 566):** "A suspensão do processo por falta de
  localização do devedor ou de bens penhoráveis (art. 40 da LEF) é
  condição necessária para o início do prazo de prescrição intercorrente,
  que será de 5 anos, nos termos do art. 174 do CTN."

  **Ementa:**
  ```
  PROCESSUAL CIVIL E TRIBUTÁRIO. RECURSO ESPECIAL REPETITIVO.
  EXECUÇÃO FISCAL. PRESCRIÇÃO INTERCORRENTE. ART. 40 DA LEI
  6.830/80. [...]
  ```

  ## REsp 1.834.175/SC (2021)

  - **Relator:** Min. Herman Benjamin
  - **Julgamento:** 23/03/2021
  - **Órgão:** 2ª Turma

  **Decisão:** Reafirma o Tema 566. O prazo de 1 ano de suspensão +
  5 anos de prescrição é contado a partir da não localização do
  devedor, não da citação.

  [...]

  ---

  ## CONCLUSÃO

  O STJ consolidou no Tema 566 (Recurso Repetitivo) que a prescrição
  intercorrente na execução fiscal exige:
  1. Suspensão do processo por 1 ano (art. 40, LEF);
  2. Decorridos mais 5 anos, configura-se a prescrição;
  3. Total: 6 anos contados da não localização do devedor/bens.

  A Súmula 314/STJ permanece aplicável: é necessário ouvir a Fazenda
  Pública antes de decretar a prescrição intercorrente.
```

---

## Testing

Test file: `tests/test_jurisprudencia.py`

Test cases:
- `test_build_messages_defaults` — only `consulta` provided; `tribunal` and `periodo` use defaults in prompt
- `test_build_messages_all_params` — all 4 params (consulta, tribunal, periodo, formato) injected into prompt
- `test_build_messages_tribunal_stf` — tribunal=stf reflects STF constraint in user message
- `test_build_messages_tribunal_todos` — tribunal=todos generates unrestricted search prompt
- `test_build_messages_tribunal_label_resolved` — TRIBUNAL_LABELS dict correctly maps stf→"STF — Supremo Tribunal Federal"
- `test_build_messages_periodo` — periodo value appears in user message
- `test_build_messages_periodo_none` — omitted periodo → "sem restrição" in user message
- `test_build_messages_returns_list_of_dicts` — output is `list[dict]` with role/content keys
- `test_build_messages_system_role_first` — first message has `role: "system"`
- `test_empty_consulta_rejected` — empty string → validation error with descriptive message
- `test_consulta_too_short_rejected` — < 5 chars → validation error
- `test_consulta_whitespace_only_rejected` — "   " → validation error
- `test_tribunal_choices_count` — exactly 11 choices (todos + 10 courts)
- `test_tribunal_choices_count_within_discord_limit` — ≤ 25 options
- `test_format_choices_count` — exactly 2 choices (texto, docx)
- `test_system_prompt_contains_court_domains` — STF/STJ/TST portal URLs in system prompt
- `test_system_prompt_contains_anti_hallucination` — system prompt includes "NUNCA invente"
- `test_system_prompt_contains_conclusao_section` — system prompt requires CONCLUSÃO section
- `test_tool_schemas_defined` — JURISPRUDENCIA_TOOLS contains web_search and fetch_page
- `test_tool_schemas_valid_openai_format` — each tool has type, function.name, function.parameters
- `test_sanitize_filename` — slug generation from consulta string

Fakes follow existing pattern from `tests/test_bot_utils.py` (dataclass-based with `cast()`).

---

## Out of Scope & Future Enhancements

### Out of Scope (v1)
- Direct API access to STF/STJ databases (push, jurisprudencia.stj.jus.br API endpoints)
- Google Scholar integration — DuckDuckGo web search only
- Lookup by case number (e.g., "RE 1.234.567") — topic-based search only
- PDF attachment of full decision texts
- Follow-up refinement messages ("busque mais sobre súmula X", "filtre apenas 2024")
- Side-by-side multi-court comparison view
- Citation index / forward-reference tracking ("citado por 15 decisões posteriores")
- ODT output format — DOCX only for file export
- Streaming output — non-streaming with heartbeat only
- `modo_pensamento` toggle — no thinking model routing in v1

### Future Enhancements
- Direct STF/STJ API integration for authoritative results and structured metadata
- Case number lookup (`/jurisprudencia numero="RE 1.234.567"`)
- PDF export with full decision text attachments
- Follow-up refinement messages in the same thread
- Multiple court comparison view (tribunal=stf,tst side-by-side)
- Súmula vinculante and tese de repercussão geral lookup by topic number
- Ementa-only mode (compact view for quick scanning)
- Result count cap with "show more" pagination
- Streaming output for long research documents
- Thinking model routing for deep jurisprudential analysis (`modo_pensamento` parameter)
- User-provided attachments as source material (complement search with uploaded PDFs)
