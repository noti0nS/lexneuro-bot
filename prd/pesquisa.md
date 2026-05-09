# PRD: `/pesquisa` — Gerador de Documentos de Pesquisa ABNT

## Overview

### Purpose
Generate structured ABNT-compliant research documents from a short topic string. Web search runs autonomously via LLM tool calling (DuckDuckGo). Focused on law and programming research — no persona switching, no NPJ/Peça Jurídica.

### Target Users
Brazilian law students and legal professionals producing ABNT papers, and developers producing technical documentation.

---

## User Flow

```
1. User invokes /pesquisa tema="assédio moral no teletrabalho"
   extensao=padrao paginas=5 modo_pensamento=True format=docx
2. Bot responds ephemeral: "Pesquisando e gerando o documento..."
3. LLM performs self-Q&A refinement (~3-5 clarifying questions, ~5-10s)
4. LLM searches the web autonomously (web_search + fetch_page),
   then generates a structured ABNT document
5. Bot sends DOCX/ODT file attachment (or threaded messages if >8MB)
```

---

## Slash Command Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `tema` | STRING | Yes | — | Main research topic in free text. Ex: "alvará judicial no TJSP aprofundado" |
| `extensao` | STRING (Choice) | No | `padrao` | Depth preset: `curto` (~1 pág. / 500w), `padrao` (~3 págs. / 1500w), `completo` (5+ págs. / 2500+w) |
| `paginas` | INTEGER | No | `3` | Target page count (1–50). Takes precedence over `extensao` when conflicting. |
| `modo_pensamento` | BOOLEAN | No | `False` | Switches to reasoning model (configurable via `research.thinking_model`) |
| `format` | STRING (Choice) | No | `docx` | Output file format: `docx` or `odt` |

5 parameters (down from 7). Removed: `contexto` (no more academico/npj/programacao), `instrucoes_extras`.

---

## Core Feature Specifications

### Simplified System Prompt

A single prompt covers both law and programming research. No persona switching — the LLM detects domain from the topic. ABNT rules apply to both.

```
Você é o LexNeuro, um assistente de pesquisa e documentação técnica.
Sua missão é inferir a intenção do usuário a partir de instruções \
fragmentadas e produzir um documento final perfeitamente estruturado \
em formato ABNT, sem exigir explicações adicionais.

### PARÂMETROS DA SOLICITAÇÃO:
- Tema Central: {tema}
- Extensão Desejada: {extensao_label} (Adeque o nível de detalhe para \
atingir essa proporção aproximada de texto).
- Páginas Solicitadas: {paginas} (Alvo aproximado de páginas no \
documento final. Priorize este número sobre a extensão se houver conflito).
- Modo de Pensamento Ativo: {modo_pensamento} (Se True, explore teses \
minoritárias e debates profundos).

### DOMÍNIOS:
- Se o tema for jurídico: produza um artigo acadêmico com doutrina, \
jurisprudência e fundamentação legal precisa. Nunca invente jurisprudência \
ou fontes inexistentes.
- Se o tema for de programação/tecnologia: produza documentação técnica \
com explicações conceituais e exemplos de código quando relevante.
- Em ambos os casos: siga rigorosamente a formatação ABNT.

### REGRAS DE EXECUÇÃO:
1. COMPREENSÃO DE FRAGMENTOS: Infira a intenção e escreva imediatamente \
o documento estruturado.
2. MARKDOWN DISCORD: Use `#` para grandes divisões e `**` para destacar \
artigos de lei (ex: **Art. 319 do CPC**). Use `>` para simular recuos de \
citação direta longa (ABNT).
3. RIGOR: Indique competência correta e fundamentação real. Se houver \
divergência, exponha ambas as correntes.
4. TOM: Direto, culto e resolutivo. Vá direto ao documento final.

### FERRAMENTAS DE PESQUISA:
Você tem acesso a `web_search` (busca DuckDuckGo por artigos, \
jurisprudência, doutrina) e `fetch_page` (conteúdo integral de URLs). \
Use múltiplas buscas com diferentes ângulos. Reúna fontes antes de \
redigir. Priorize fontes confiáveis: doutrina, jurisprudência oficial, \
artigos acadêmicos.

### FORMATAÇÃO:
- Use notas de rodapé numeradas (¹, ²) com citações ABNT.
- Inclua "REFERÊNCIAS" ao final em ABNT NBR 6023.
- Produza APENAS o conteúdo do documento — sem comentários fora do documento.
```

ABNT reference from `abnt_reference.md` is appended after the system prompt (unchanged).

### Extensão & Páginas Interaction

| extensao | Word Count Target |
|----------|-------------------|
| `curto` | ~500 palavras |
| `padrao` | ~1.500 palavras |
| `completo` | ~2.500+ palavras |

When `paginas` differs from the extensao preset's implied page count, `paginas` takes precedence. Both values are injected into the prompt.

### Pre-Generation Refinement (Self-Q&A)

Unchanged from v2. Before the tool-calling loop, the bot makes a single non-streaming call with `tool_choice="none"` asking the LLM to formulate and answer 3-5 clarifying questions about the topic (Análise Preliminar). Output is appended as an assistant message, enriching context for the subsequent research loop.

**Gating:** `research.refinement_enabled` (default `true`). When `false`, skip refinement and start the tool loop immediately.

Refinement prompt (unchanged from v2):
```
Antes de iniciar a pesquisa, reflita sobre o tema. Formule de 3 a 5 \
perguntas esclarecedoras que um especialista faria e responda cada uma \
com seu melhor conhecimento jurídico. Seja conciso. Não faça buscas — \
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

### Web Search via LLM Tool Calling

- `web_search(query)` — DuckDuckGo search, returns title/url/snippet
- `fetch_page(url)` — full page content (up to 8.000 chars)
- Loop limited by `research.max_tool_iterations` (default 15)
- `search_results_per_topic`: 8 results per query
- `max_page_fetches`: 5 pages total
- If loop exhausts, force final call with `tool_choice="none"`

**No upfront search** — the LLM decides when and what to search.

### Thinking Model Routing

| Condition | Model Used |
|-----------|-----------|
| `modo_pensamento=False` | `state.curr_model` (global, set via `/model`) |
| `modo_pensamento=True` + config has `research.thinking_model` | Config value (e.g. `deepseek/deepseek-r1`) |
| `modo_pensamento=True` + no config key | Falls back to `state.curr_model` + log warning |

### LLM Call Pattern

Two-phase non-streaming with `await_task_with_heartbeats` (unchanged from v2):

**Phase 1 — Refinement (if `research.refinement_enabled` is `true`):**
- Single call with `tool_choice="none"` and refinement prompt
- Output appended as assistant message to `messages[]`

**Phase 2 — Research & Generation:**
- Tool-calling loop with `web_search` + `fetch_page` tools
- `finish_reason == "stop"` + content → document complete, exit
- `finish_reason == "tool_calls"` → execute searches, append results, continue
- `finish_reason == "length"` → capture content, exit
- `finish_reason == "content_filter"` → ephemeral error
- If loop exhausts → force final call with `tool_choice="none"`

### File Output & Delivery

Unchanged from v2:
- DOCX via `python-docx` + pandoc, ABNT margins applied
- ODT via `odfpy` + pandoc
- Filename: `pesquisa_[slug]_[timestamp].[ext]`
- ≤8MB → Discord file attachment
- >8MB → Thread with chunked messages

---

## Configuration

```yaml
# config-example.yaml — unchanged
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
| `research.refinement_enabled` | `true` | Whether to run the pre-generation self-Q&A refinement call |

Config is hot-reloaded on every invocation via `await asyncio.to_thread(get_config)`. No caching.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/commands/pesquisa.py` | **Edit** — Remove `contexto` and `instrucoes_extras` params; remove `CONTEXTO_CHOICES`; keep refinement, thinking model routing, tool loop, file delivery as-is |
| `src/prompts/pesquisa.py` | **Edit** — Remove `CONTEXTO_LABELS`, `_CONTEXTO_GUIDANCE`; rewrite `PESQUISA_SYSTEM_PROMPT` without `{contexto_label}`, `{contexto_guidance}`; simplify `build_pesquisa_messages()` signature (drop `contexto`, `instrucoes_extras` params); keep `REFINEMENT_PROMPT` and `build_refinement_message()` |
| `config-example.yaml` | **No change** — `research:` section unchanged |
| `tests/test_pesquisa.py` | **Edit** — Remove contexto/NPJ tests; update prompt tests to match simplified signature |

---

## Edge Cases & Error Handling

| Case | Behavior |
|------|----------|
| Empty `tema` | Ephemeral: "Descreva sua pesquisa." |
| `paginas` < 1 | Ephemeral: "O número de páginas deve ser no mínimo 1." |
| `paginas` > 50 | Ephemeral: "O número de páginas não pode exceder 50." |
| `modo_pensamento=True` but no `thinking_model` config | Fallback to `state.curr_model`, log warning |
| Refinement call fails (APIError) | Log warning, skip refinement, proceed directly to tool loop |
| Refinement call returns empty output | Log warning, skip refinement append, proceed to tool loop |
| `refinement_enabled=false` | Skip refinement entirely, start tool loop immediately |
| LLM returns document without searching | Accept and proceed |
| Search returns no results | Return `[]` in tool response; LLM may retry or use training knowledge |
| Search throws exception | Return error string in tool response; LLM may retry |
| `fetch_page` fails | Return error string; LLM may try another URL |
| `fetch_page` exceeds `max_page_fetches` limit | Return limit message; LLM continues with available sources |
| Tool loop exceeds `max_tool_iterations` | Force final call with `tool_choice="none"` |
| LLM returns `finish_reason="length"` | Capture partial content, exit loop |
| LLM returns `finish_reason="content_filter"` | Ephemeral error to user |
| LLM returns empty output | Ephemeral: "Não foi possível gerar o conteúdo do documento." |
| Provider error (APIError) | `followup.send()` with provider detail |
| File > 8MB | Thread delivery with chunked messages |
| `generate_document` fails | Send raw text in messages instead |

---

## Example Interaction

```
User:
  /pesquisa tema="assédio moral no teletrabalho pós-pandemia"
            extensao="Padrão (~3 págs. / 1.500w)"
            paginas=5
            modo_pensamento=True
            format=docx

Bot (ephemeral):
  Pesquisando e gerando o documento... Isso pode levar alguns minutos.

  [LLM self-Q&A refinement: formulates 4 clarifying questions about
   legal framework, jurisprudential trends, burden of proof, and
   comparative labor law — answers from training knowledge]

  [LLM searches: "assédio moral teletrabalho jurisprudência TST",
   "teletrabalho CLT reforma trabalhista art. 75-B", fetches 3 pages,
   switches to DeepSeek-R1 for deep reasoning, generates 5-page ABNT
   document with structured legal analysis]

Bot (followup):
  Pesquisa concluída! Aqui está o documento:
  📎 pesquisa_assedio_moral_no_teletrabalho_20260509_143022.docx
```

---

## Testing

Test file: `tests/test_pesquisa.py`

- `test_build_messages_defaults` — only `tema`, all defaults interpolated into prompt
- `test_build_messages_all_params` — all 5 params injected into prompt
- `test_build_messages_paginas_in_prompt` — `paginas` value appears in system prompt
- `test_build_messages_extensao_curto` — extensao=curto reflects ~500w constraint
- `test_build_messages_extensao_completo` — extensao=completo reflects 2500+w constraint
- `test_build_messages_modo_pensamento_true` — modo_pensamento=True appears in prompt
- `test_build_messages_includes_abnt_reference` — ABNT reference appended to system prompt
- `test_build_messages_returns_list_of_dicts` — output is `list[dict]` with role/content keys
- `test_build_messages_no_contexto_param` — `contexto` no longer a parameter of `build_pesquisa_messages()`
- `test_build_messages_no_instrucoes_extras_param` — `instrucoes_extras` no longer a parameter
- `test_empty_tema_rejected` — empty string → validation error
- `test_extensao_choices_count` — exactly 3 choices
- `test_format_choices_count` — exactly 2 choices
- `test_build_pesquisa_filename` — filename sanitization + timestamp pattern
- `test_thinking_model_routing` — modo_pensamento=True routes to thinking_model from config
- `test_thinking_model_fallback` — missing config key falls back to state.curr_model
- `test_refinement_prompt_built` — refinement prompt contains "ANÁLISE PRELIMINAR"
- `test_refinement_disabled` — refinement_enabled=false skips the self-Q&A call

Fakes follow existing pattern from `tests/test_bot_utils.py` (dataclass-based with `cast()`).

---

## Out of Scope & Future Enhancements

### Removed from v2

- `contexto` parameter and persona switching (academico/npj/programacao) — the LLM detects domain from the topic
- `instrucoes_extras` parameter — removed to simplify UX
- NPJ / Peça Jurídica persona — the command focuses on research documents, not legal procedural pieces

### Out of Scope (v1)

- User-provided attachments as sources
- Citation database / reference manager integration
- PDF output format
- Streaming generation
- Follow-up refinement messages
- Multiple provider fallback for thinking model

### Future Enhancements

- PDF output format
- Hard page count enforcement via token/character budgeting
- `/pesquisa` refinement via follow-up messages
- Multiple thinking model fallback chain
- Citation style customization (ABNT alternatives)
- Web search provider swapping (beyond DuckDuckGo)
