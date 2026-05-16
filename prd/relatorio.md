# PRD: `/relatorio` — Gerador de Relatórios Acadêmicos

## Overview

### Purpose
Generate a structured academic report (relatório teórico) from a title, description, and optional topic/section scaffolding. Supports optional web research via DuckDuckGo (shared infrastructure with `/pesquisa`) and file uploads (PDF, DOCX, ODT, TXT) as source material. Outputs a formal report in PDF, DOCX, or ODT format — distinct from the ABNT research documents produced by `/pesquisa`.

### Target Users
Brazilian university students who need to produce explanatory reports on academic topics (computer science, engineering, law, etc.). The LLM explains each topic thoroughly, organizes content into logical sections, and delivers a ready-to-submit document — with or without web research.

---

## User Flow

```
1. User invokes /relatorio titulo="Árvores B, B+, Heap e Trie"
                      descricao="O objetivo deste trabalho..."
                      topicos="Árvore B, Árvore B+, Heap, Trie"
                      paginas=4 pesquisar=False formato=docx
                      [optional: arquivo=assignment.pdf]
2. Bot responds ephemeral: "Gerando o relatório..."
3. [If arquivo provided] Bot downloads and extracts text via markitdown
4. [If pesquisar=True] LLM performs web search loop (shared infra with /pesquisa)
5. [If pesquisar=False] Single non-streaming LLM call
6. Bot generates document file (PDF/DOCX/ODT) and sends as attachment
```

---

## Slash Command Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `titulo` | STRING | Yes | — | Report title. Ex: "Árvores B, B+, Heap e Trie" |
| `descricao` | STRING | Yes | — | Report description / assignment instructions. Ex: "O objetivo deste trabalho é aprofundar o conhecimento teórico..." |
| `topicos` | STRING | No | — | Comma-separated topics to cover. Ex: "Árvore B, Árvore B+, Heap, Trie". If omitted, LLM infers from descricao. |
| `secoes` | STRING | No | — | Comma-separated section headers to apply to each topic. Ex: "Definição, Regras, Complexidade, Usos Comuns". If omitted, LLM decides section structure. |
| `paginas` | INTEGER | No | `6` | Target page count (1–50). |
| `pesquisar` | BOOLEAN | No | `False` | Enable web research (DuckDuckGo tool loop). When False, LLM generates from training knowledge only. |
| `arquivo` | ATTACHMENT | No | — | Uploaded file (.pdf, .docx, .odt, .txt) with assignment instructions or source material. Use `markitdown` for extraction (already a dependency via `/peca`). |
| `instrucoes` | STRING | No | — | Extra instructions. Ex: "foco em comparação com BST e AVL", "incluir diagramas conceituais". |
| `formato` | STRING (Choice) | No | `docx` | Output file format: `pdf`, `docx`, or `odt`. |

9 parameters. At least one of `topicos`, `secoes`, or `arquivo` should guide the LLM — but none are strictly required beyond `titulo` and `descricao`. The LLM can infer structure from the descricao alone.

---

## Core Feature Specifications

### Shared Research Infrastructure

The web search + tool-calling loop currently embedded in `src/commands/pesquisa.py` will be extracted into `src/helpers/research.py` as a reusable helper. Both `/pesquisa` and `/relatorio` will import from it.

```python
# src/helpers/research.py (new module)

async def run_research_loop(
    openai_client,
    openai_config: dict,
    messages: list[dict[str, Any]],
    *,
    max_iterations: int,
    search_results_per_topic: int,
    max_page_fetches: int,
    tools: list[dict[str, Any]] = ALL_PESQUISA_TOOLS,
    reasoning_effort: str | None = None,
    user_id: int,
) -> str:
    """Run the tool-calling loop (web_search + fetch_page).
    Returns the final generated text.
    Raises APIError on provider errors.
    """
    ...
```

The `ALL_PESQUISA_TOOLS`, `_format_tool_call`, `_format_search_results` functions move to `research.py` as well. `/pesquisa` calls this helper after its optional refinement phase. `/relatorio` calls it only when `pesquisar=True`.

**`/pesquisa` impact:** minimal refactor — replace the inline loop with a call to `run_research_loop()`. All existing behavior (refinement, thinking model routing, error handling) stays in `pesquisa.py`.

### System Prompt Design

The system prompt lives in `src/prompts/relatorio.py`. It instructs the LLM to act as an academic report writer — not a legal specialist, not an ABNT formatter.

```
Você é um redator de relatórios acadêmicos. Você produz relatórios \
teóricos bem organizados, completos e prontos para entrega — sem \
exigir que o usuário forneça cada detalhe.

Sua tarefa: a partir do título, descrição, tópicos e seções fornecidos, \
escrever um relatório acadêmico formal que explique cada tópico com \
profundidade adequada ao nível de ensino (graduação/pós-graduação).

### PARÂMETROS DA SOLICITAÇÃO
- Título: {titulo}
- Autor: {autor} (nome do usuário no Discord)
- Data: {data} (data atual formatada)
- Páginas Solicitadas: {paginas} — ALVO EXATO. O documento DEVE ter \
{paginas} página(s) de conteúdo. Planeje a estrutura antes de redigir.
- Tópicos: {topicos}
- Seções por Tópico: {secoes}
- Pesquisa Web: {pesquisar_label}

### REGRAS DE ESTRUTURA
1. Se tópicos e seções forem fornecidos: para CADA tópico, crie as seções \
   especificadas. O LLM decide a profundidade de cada seção para atingir \
   a contagem de páginas.
2. Se apenas tópicos forem fornecidos (sem seções): o LLM decide quais \
   seções fazem sentido para cada tópico.
3. Se nenhum tópico nem seção forem fornecidos: o LLM extrai a estrutura \
   da descrição e decide tudo.
4. Se apenas seções forem fornecidas (sem tópicos): o LLM infere os tópicos \
   da descrição e aplica as seções a cada um.

### ESTRUTURA DO RELATÓRIO
- Capa/primeira página: título do trabalho, nome do autor, data
- Sumário (se o relatório tiver 3+ páginas)
- Para cada tópico: seções conforme especificado ou inferido
- Conclusão / Considerações Finais
- Referências (se pesquisa web foi usada ou se fontes forem citadas)

### REGRAS DE REDAÇÃO
1. **Tom acadêmico, acessível.** Nem pedante, nem coloquial. Explique \
   conceitos como se estivesse ensinando um colega de turma.
2. **Clareza acima de erudição.** Prefira explicações diretas com exemplos \
   a jargão sem contexto.
3. **Markdown do Discord:** Use `#` para título principal, `##` para \
   tópicos, `###` para seções, `**` para conceitos-chave.
4. **Diagramas textuais:** Se relevante, represente estruturas com ASCII \
   art ou descrições textuais claras (ex: árvores, heaps, tries).
5. **Exemplos:** Para cada conceito, inclua pelo menos um exemplo concreto.
6. **NÃO invente fatos.** Se não souber algo com certeza, indique a incerteza. \
   Se pesquisa web estiver ativada, use-a para verificar informações.
7. **Responda APENAS com o relatório** — sem introduções como "Aqui está", \
   sem comentários meta-textuais.

### FORMATAÇÃO
- Título centralizado no topo (formato: # Título)
- Autor e data abaixo do título
- Seções numeradas ou com headings hierárquicos
- Tabelas em markdown quando apropriado (ex: comparação de complexidades)
- Código em blocos ``` quando relevante
```

#### User message template

```
Descrição do trabalho:
{descricao}

{instrucoes_block}

{fonte_arquivo_block}
```

Where:
- `{instrucoes_block}` is `Instruções adicionais:\n{instrucoes}` if provided
- `{fonte_arquivo_block}` is `### FONTE (extraída do arquivo)\n\n{extracted_text}` if an arquivo was uploaded

### Author Metadata

Author name is extracted from `interaction.user.display_name` (Discord display name, which may differ from username). No parameter for it — it's automatic. The current date is injected into the system prompt via `datetime.now().strftime("%d de %B de %Y")` (Portuguese locale).

### Extensão & Páginas Interaction

No `extensao` parameter. The `paginas` parameter is the sole sizing constraint. The LLM is instructed to target exactly that many pages by adjusting section depth. Default is 6 pages (longer than `/pesquisa`'s default of 3, reflecting that reports tend to be multi-topic).

### File Input Extraction

When `arquivo` is provided, the bot downloads the attachment via `httpx.AsyncClient` and extracts text using `markitdown` (already installed for `/peca` — no new dependency):

```
arquivo → httpx download → BytesIO → MarkItDown().convert_stream() → markdown_text
```

Supported input types: `.pdf`, `.docx`, `.odt`, `.txt`.

Suffix pattern:
| Extension | Content Type |
|-----------|-------------|
| `.pdf` | `application/pdf` |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `.odt` | `application/vnd.oasis.opendocument.text` |
| `.txt` | `text/plain` |

If the file has no extension or an unknown content type, the bot replies ephemeral with supported types.

Extracted text is truncated to `relatorio.max_fonte_chars` (default 75000) with a warning log. The truncated text is injected into the user message under a `### FONTE (extraída do arquivo)` marker.

### Web Research (Optional)

When `pesquisar=True`, the research loop runs identically to `/pesquisa` phase 2:
- `web_search` + `fetch_page` tools
- Limited by `relatorio.max_tool_iterations` (default 15)
- Same DuckDuckGo backend, same page fetch limits
- No refinement phase — the descricao already serves as the briefing

Config keys under a `relatorio:` section:
```yaml
relatorio:
  max_tool_iterations: 15
  search_results_per_topic: 8
  max_page_fetches: 5
  max_fonte_chars: 75000
  default_paginas: 6
```

When `pesquisar=False` (default), the LLM call is a single non-streaming completion with `tool_choice="none"`. No web search tools are passed.

### LLM Call Pattern

**When `pesquisar=False`:**
1. Build messages via `build_relatorio_messages(...)`
2. Single non-streaming call with `await_task_with_heartbeats`
3. No tools, no loop. Extract content, generate document.

**When `pesquisar=True`:**
1. Build messages via `build_relatorio_messages(...)`
2. Call `run_research_loop()` from `src/helpers/research.py`
3. Receive final text, generate document.

Error handling mirrors `/pesquisa`: APIError → provider detail in followup; empty output → ephemeral error; content_filter → ephemeral error; file generation failure → fallback to raw text.

### Model Resolution

Follows the same pattern as `/pesquisa`, `/peca`, and `/jurisprudencia`:

```python
relatorio_config = state.config.get("relatorio", {})
model = relatorio_config.get("model")
curr_model = model if model else state.curr_model
openai_client, openai_config = get_openai_config(state.config, curr_model)
```

| Condition | Model Used |
|-----------|-----------|
| `relatorio.model` is set in config | Config value (e.g. `openai/gpt-5`) |
| `relatorio.model` is not set | `state.curr_model` (global, set via `/model`) |

No thinking model routing — reports use a single model regardless of `pesquisar`. If `pesquisar=True`, the same model runs both the tool loop and the final generation.

### File Output & Delivery

Reuses the existing document pipeline from `src/helpers/documents.py`:
- DOCX: ABNT margins + Times New Roman via `_apply_abnt()`
- ODT: pandoc markdown → ODT
- PDF: pandoc with pdflatex engine

Filename: `relatorio_[slug]_[user_id]_[timestamp].[ext]`

Delivery via `send_document_result()` (same helper used by `/pesquisa` and `/peca`):
- ≤7.5MB → Discord file attachment
- >7.5MB → Thread with chunked messages

---

## Configuration

```yaml
# config-example.yaml additions
relatorio:
  max_tool_iterations: 15
  search_results_per_topic: 8
  max_page_fetches: 5
  max_fonte_chars: 75000
  default_paginas: 6
  model:                         # optional override; falls back to /model global
```

| Key | Default | Purpose |
|-----|---------|---------|
| `relatorio.max_tool_iterations` | `15` | Max web search loop iterations (only when `pesquisar=True`) |
| `relatorio.search_results_per_topic` | `8` | Results per DuckDuckGo search |
| `relatorio.max_page_fetches` | `5` | Max pages fetched via `fetch_page` tool |
| `relatorio.max_fonte_chars` | `75000` | Max characters from uploaded file before truncation |
| `relatorio.default_paginas` | `6` | Default page count when user omits `paginas` |
| `relatorio.model` | (none) | Optional model override. Falls back to `state.curr_model`. Format: `provider/model`. |

Config is hot-reloaded on every invocation via `await asyncio.to_thread(get_config)`. No caching.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `prd/relatorio.md` | **Create** — this PRD |
| `src/commands/relatorio.py` | **Create** — slash command registration, input validation, file extraction, LLM orchestration, file delivery |
| `src/prompts/relatorio.py` | **Create** — `RELATORIO_SYSTEM_PROMPT`, `build_relatorio_messages()` |
| `src/prompts/__init__.py` | **Edit** — add export for `build_relatorio_messages` |
| `src/helpers/research.py` | **Create** — extracted `run_research_loop()`, `ALL_PESQUISA_TOOLS`, `_format_tool_call`, `_format_search_results` |
| `src/commands/pesquisa.py` | **Edit** — refactor to use `run_research_loop()` from `src/helpers/research.py` |
| `src/bot.py` | **Edit** — import and call `register_relatorio_command(...)`; pass `httpx_client` |
| `config-example.yaml` | **Edit** — add `relatorio:` section |
| `pyproject.toml` | **No change** — `markitdown` already present for `/peca`; `httpx` already present |
| `tests/test_relatorio.py` | **Create** — unit tests for prompt building, validation, and message construction |
| `tests/test_research.py` | **Create** — unit tests for the extracted research loop helper |

---

## Edge Cases & Error Handling

| Case | Behavior |
|------|----------|
| Empty `titulo` | Ephemeral: "Informe um título para o relatório." |
| Empty `descricao` | Ephemeral: "Descreva o objetivo do relatório." |
| `paginas` < 1 | Ephemeral: "O número de páginas deve ser no mínimo 1." |
| `paginas` > 50 | Ephemeral: "O número de páginas não pode exceder 50." |
| Both `topicos` and `secoes` empty, no `arquivo` | OK — LLM infers structure from `descricao` alone |
| `arquivo` is not a supported type | Ephemeral: "Tipo de arquivo não suportado. Envie .pdf, .docx, .odt ou .txt." |
| `arquivo` download/read fails | Ephemeral: "Não consegui ler o arquivo. Verifique se ele é válido." |
| Extracted file text is empty | Ephemeral: "O arquivo parece estar vazio." |
| Extracted text exceeds `relatorio.max_fonte_chars` | Truncate, log warning, proceed |
| `pesquisar=True` but search returns no results | Return `[]` in tool response; LLM retries or uses training knowledge |
| `pesquisar=True` but tool loop exhausts | Force final call with `tool_choice="none"` |
| `pesquisar=True` but `fetch_page` fails | Return error string; LLM tries another URL |
| LLM returns empty output | Ephemeral: "Não foi possível gerar o conteúdo do relatório." |
| LLM returns `finish_reason="content_filter"` | Ephemeral: "A geração foi bloqueada pelo filtro de conteúdo do provedor." |
| Provider error (APIError) | `followup.send(...)` with provider detail |
| File > 7.5MB | Thread delivery with chunked messages |
| `generate_document` fails | Send raw text in messages instead |
| `formato=pdf` but pdflatex not installed | `generate_document` raises RuntimeError → bot sends error with suggestion to use DOCX or ODT |
| User doesn't have permission | `user_has_permission(...)` check. Ephemeral rejection. |
| `topicos` has many topics (10+) with `pesquisar=True` | Tool loop may run longer; natural throttle via `max_tool_iterations` |
| Very long `descricao` (>50000 chars) | Not truncated — sent as-is (Discord slash command string limit is 4000 chars for STRING params, so this is self-limiting) |

---

## Example Interaction

```
User:
  /relatorio titulo="Árvores B, B+, Heap e Trie"
             descricao="O objetivo deste trabalho é aprofundar o conhecimento
             teórico sobre estruturas de dados avançadas amplamente usadas em
             bancos de dados, organização de arquivos, sistemas de busca e
             indexação de strings."
             topicos="Árvore B, Árvore B+, Heap, Trie"
             paginas=4
             pesquisar=False
             formato=pdf

Bot (ephemeral):
  Gerando o relatório... Isso pode levar alguns minutos.

  [Single non-streaming LLM call — no web search]

Bot (followup):
  Relatório concluído! Aqui está o documento:
  📄 relatorio_arvores_b_b+_heap_e_trie_20260516_143022.pdf
```

**Generated document outline:**
```
# Árvores B, B+, Heap e Trie

**Autor:** José da Silva
**Data:** 16 de maio de 2026

---

## 1. Árvore B

### 1.1 Definição e Funcionamento Básico
A Árvore B é uma estrutura de dados de árvore balanceada...

### 1.2 Regras e Balanceamento
Cada nó interno (exceto a raiz) deve conter entre ⌈m/2⌉ e m filhos...

### 1.3 Usos Comuns
- Bancos de dados relacionais (índices)
- Sistemas de arquivos (NTFS, ext4, HFS+)

### 1.4 Complexidade das Operações
| Operação | Complexidade |
|----------|-------------|
| Busca    | O(log n)     |
| Inserção | O(log n)     |
| Remoção  | O(log n)     |

...

## 5. Conclusão

[Comparação final entre as quatro estruturas...]

## Referências

[Fontes citadas — se pesquisa web tiver sido usada]
```

### Example Interaction (with file upload + web research)

```
User:
  /relatorio titulo="Impacto da IA no Mercado de Trabalho"
             descricao="Analisar os efeitos da inteligência artificial..."
             topicos="Automação, Novas profissões, Desigualdade"
             paginas=8
             pesquisar=True
             [uploads trabalho_instrucoes.pdf]
             formato=docx

Bot (ephemeral):
  Gerando o relatório...

  [Downloads PDF, extracts text via markitdown]
  [Runs research loop: 12 web searches, 4 page fetches]
  [Generates 8-page DOCX with full report]

Bot (followup):
  Relatório concluído! Aqui está o documento:
  📘 relatorio_impacto_da_ia_no_mercado_de_trabalho_20260516_150530.docx
```

---

## Testing

Test file: `tests/test_relatorio.py`

- `test_build_messages_minimal` — only `titulo` and `descricao`, all optional params default
- `test_build_messages_all_params` — all 9 parameters injected into messages
- `test_build_messages_autor_in_prompt` — `autor` appears in system prompt
- `test_build_messages_data_in_prompt` — current date appears in system prompt
- `test_build_messages_topicos_interpolated` — topicos string appears in system prompt
- `test_build_messages_secoes_interpolated` — secoes string appears in system prompt
- `test_build_messages_pesquisar_true` — `pesquisar=True` reflected in prompt
- `test_build_messages_pesquisar_false` — `pesquisar=False` reflected in prompt
- `test_build_messages_returns_list_of_dicts` — output is `list[dict]` with role/content keys
- `test_build_messages_descricao_as_user_message` — descricao appears in user message
- `test_build_messages_instrucoes_block` — instrucoes appear in user message when provided
- `test_build_messages_instrucoes_omitted` — no instrucoes block when not provided
- `test_empty_titulo_rejected` — empty string → validation error
- `test_empty_descricao_rejected` — empty string → validation error
- `test_paginas_below_1_rejected` — paginas < 1 → ephemeral error
- `test_paginas_above_50_rejected` — paginas > 50 → ephemeral error
- `test_format_choices_count` — exactly 3 choices (pdf, docx, odt)
- `test_build_relatorio_filename` — filename sanitization + timestamp + user_id pattern
- `test_attachment_not_supported` — non-pdf/docx/odt/txt attachment → validation error
- `test_fonte_truncated_when_over_max` — extracted text longer than `max_fonte_chars` is truncated with warning
- `test_pesquisar_defaults_to_false` — parameter default is False

Additional test file: `tests/test_research.py`

- `test_run_research_loop_basic` — loop produces output text
- `test_run_research_loop_tool_call_handling` — web_search and fetch_page tool calls are executed
- `test_run_research_loop_exhaustion` — loop exhausts → force final generation succeeds
- `test_run_research_loop_content_filter` — content_filter finish reason raises/handles correctly
- `test_format_tool_call` — tool call formatting matches expected dict structure
- `test_format_search_results` — search results JSON serialization

Fakes follow existing pattern from `tests/test_bot_utils.py` (dataclass-based with `cast()`).

---

## Out of Scope & Future Enhancements

### Out of Scope (v1)

- Streaming generation
- Thinking model routing (use `state.curr_model` only)
- Post-generation validation pass (LLM checking factual accuracy)
- Self-Q&A refinement phase (like `/pesquisa`'s refinement — the descricao already serves this role)
- Interactive follow-up: user replies "add section X" and the bot regenerates
- Custom citation styles (ABNT, APA, IEEE)
- Multiple file uploads
- Image/diagram inclusion in output (would require vision model + pandoc image embedding)

### Future Enhancements

- Self-Q&A refinement for complex reports (like `/pesquisa`'s refinement)
- Thinking model routing for `pesquisar=True` (use `relatorio.thinking_model` config)
- Citation manager: auto-format references in ABNT/APA/IEEE
- Interactive refinement: follow-up messages to add/remove sections
- Multiple file uploads for source material
- Streaming generation for better UX on long reports
- Embedded diagram generation (LLM generates PlantUML/Mermaid, bot renders to image)
- Template system: save/reuse report structures
