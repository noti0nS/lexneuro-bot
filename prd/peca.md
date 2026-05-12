# PRD: `/peca` — Gerador de Peças Processuais

## Overview

### Purpose
Generate a complete, academically rigorous legal procedural piece (petição inicial, contestação, apelação, etc.) from a free-text case statement or an uploaded document file (PDF, DOCX, ODT). The LLM interprets the input, identifies the appropriate piece type if not specified, extracts legally relevant facts, selects doctrines, structures arguments, and produces a ready-to-deliver document in PDF, DOCX, or ODT.

### Target Users
Brazilian law students producing assignments for prática jurídica (legal practice) courses or supervised internships. Also useful for legal professionals drafting initial versions of procedural pieces.

---

## User Flow

```
1. User invokes /peca:
   a) Text path: /peca enunciado="João firmou contrato..." tipo="Contestação" format=docx
   b) File path: /peca arquivo=caso_pratico.pdf tipo="Petição Inicial" area="Civil" format=docx
2. Bot responds ephemeral: "Gerando a peça processual..."
   (If file input, extracts text from PDF/DOCX/ODT first)
3. LLM generates the complete procedural piece in a single non-streaming call
4. Bot sends file attachment (PDF, DOCX, or ODT) or chunked messages if >8MB
```

---

## Slash Command Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enunciado` | STRING | No | `""` | Case statement, practical exercise, or instructions describing the legal scenario. Free text. |
| `arquivo` | ATTACHMENT | No | — | Uploaded document (.pdf, .docx, .odt) containing the case statement. |
| `tipo` | STRING | No | — | Type of procedural piece. If omitted, the LLM infers it. Examples: "Petição Inicial", "Contestação", "Apelação", "Agravo de Instrumento", "Mandado de Segurança", "Embargos de Declaração", "Recurso Especial", "Recurso Extraordinário", "Reclamação", "Exceção de Suspeição". |
| `area` | STRING | No | — | Legal area context to narrow the LLM's reasoning. Examples: "Civil", "Penal", "Trabalhista", "Tributário", "Constitucional", "Administrativo", "Empresarial", "Consumidor". |
| `instrucoes` | STRING | No | — | Extra instructions for the generation. e.g. "incluir tutela de urgência", "foco no mérito, ignorar preliminares", "argumentar por analogia com REsp 1.234.567". |
| `format` | STRING (Choice) | No | `docx` | Output file format: `pdf`, `docx`, or `odt`. |

6 parameters. At least one of `enunciado` or `arquivo` must be provided — validated at runtime. If both are provided, `enunciado` is prepended to the extracted file text.

---

## Core Feature Specifications

### System Prompt Design

The system prompt will live in `src/prompts/peca.py` following the `pesquisa.py` / `cronograma.py` pattern. It instructs the LLM to act as a Brazilian legal practice specialist and produce a single, complete procedural piece.

#### System prompt template

```
Você é um especialista em prática jurídica brasileira. Você redige \
peças processuais completas para entrega acadêmica em disciplinas de \
prática jurídica ou estágio supervisionado.

Sua peça deve ser tecnicamente correta, estrategicamente fundamentada, \
bem organizada e redigida em linguagem jurídica clara e precisa — como \
uma peça real de prática jurídica, pronta para protocolo.

### TAREFA
- Interprete o enunciado abaixo.
- Se o tipo da peça NÃO for informado, identifique a peça cabível.
- Reconheça quem é o cliente/representado e quem é a parte adversa.
- Extraia os fatos juridicamente relevantes.
- Selecione teses jurídicas adequadas ao caso.
- Fundamente com legislação, doutrina e jurisprudência pertinentes.
- Organize os argumentos em tópicos jurídicos temáticos.
- Formule pedidos coerentes, completos e numerados.
- Gere a peça processual COMPLETA no formato solicitado.

### PARÂMETROS DA SOLICITAÇÃO
- Tipo da Peça: {tipo} (inferido se não especificado)
- Área do Direito: {area} (inferida se não especificada)
- Instruções Adicionais: {instrucoes}

### ESTRUTURA DA PEÇA
A peça deve conter, conforme cabível ao tipo:
1. **Endereçamento** — juízo/órgão competente
2. **Qualificação das partes** — quando os dados existirem no enunciado
3. **Nome correto da peça**
4. **Síntese objetiva dos fatos**
5. **Fundamentos jurídicos** organizados em tópicos temáticos
6. **Pedidos** numerados e completos
7. **Requerimento de provas** — quando cabível
8. **Valor da causa** — quando cabível
9. **Fechamento** — local, data, advogado, OAB

### REGRAS DE OURO
1. **NUNCA INVENTE DADOS.** Esta é a regra mais importante.
   Se o enunciado não trouxer informações suficientes, use placeholders:
   - Processo nº __________
   - Comarca de __________
   - ___ Vara __________
   - CPF nº __________
   - OAB/UF nº ________
   - ___ de __________ de 20__
2. **VALORES:** Se o valor estiver expressamente informado no enunciado e \
   for possível aplicar uma regra objetiva (ex: 12× aluguel para valor da \
   causa em despejo, art. 58, III, Lei 8.245/1991), você PODE calcular. \
   Se o valor não estiver claro, NÃO invente. Use "R$ XXXX" e explique o \
   critério legal que deveria ser aplicado.
3. **NOMES:** Se o enunciado mencionar "João" ou "Maria", use esses nomes. \
   Se não mencionar nomes, use "REQUERENTE" e "REQUERIDO" (ou as \
   designações processuais adequadas ao tipo da peça).
4. **SUBTÍTULOS JURÍDICOS:** Evite títulos genéricos como "Desenvolvimento" \
   ou "Do Mérito". Prefira subtítulos jurídicos maduros, como:
   - "Da Ausência de Documentos Indispensáveis"
   - "Da Responsabilidade Civil da Requerida"
   - "Do Indeferimento da Tutela de Urgência"
   - "Da Boa-fé da Parte Requerida"
   - "Da Improcedência do Pedido Autoral"
   - "Da Inépcia da Inicial"
   - "Da Prescrição Aplicável"
   - "Da Ilegitimidade Passiva"
   - "Da Inversão do Ônus da Prova"
5. **FORMATAÇÃO:** Use markdown estrutural para o Discord. \
   `#` para títulos, `##` para seções, `###` para subseções. \
   `**Art. XXX da Lei/CPC/CF**` para destaques legislativos.

### TOM E QUALIDADE
- Linguagem jurídica formal, mas clara e direta.
- A peça NÃO deve parecer um "modelo genérico da internet".
- Cada parágrafo deve ter propósito jurídico claro.
- Citações de lei devem ser precisas (número do artigo, lei, constituição).
- Se houver divergência doutrinária ou jurisprudencial relevante, \
  mencione a corrente majoritária e, se pertinente, a minoritária.

Responda APENAS com a peça processual completa — sem introduções, \
sem "claro!", sem comentários fora da peça.
```

#### User message

```text
{enunciado}
```

The user message is the raw `enunciado` string. The optional `tipo`, `area`, and `instrucoes` values are interpolated into the system prompt.

### File Input Extraction (via `markitdown`)

When the user provides an `arquivo` (PDF, DOCX, or ODT), the bot extracts text using [microsoft/markitdown](https://github.com/microsoft/markitdown) — a lightweight Python library that converts various file formats to Markdown, preserving structure (headings, lists, tables, links). Markdown is the ideal input format for LLMs.

**Why `markitdown` over format-specific extractors:**

- **PDF:** The existing `PdfProcessor.extract_text()` raises `ValueError("pdf_extraction_not_supported")`. `markitdown` handles PDF natively. No separate `pymupdf`/`pdfplumber` needed.
- **DOCX/ODT:** While the codebase already has `DocxProcessor.extract_text()` and `OdtProcessor.extract_text()` (used by `/abnt`), `markitdown` produces structured Markdown (tables, lists, headings) instead of flat paragraphs — richer context for the LLM.
- **Uniform output:** All input formats produce the same Markdown structure, simplifying the prompt.

**Installation:** `pip install 'markitdown[pdf,docx]'` — the `[pdf,docx]` extras cover the three supported input formats (pdf, docx, odt). Requires Python 3.10+ (met: project is 3.13+).

**Extraction flow:**

```
arquivo → httpx download → BytesIO → markitdown.MarkItDown().convert_stream() → markdown_text
```

The bot downloads the attachment via `httpx.AsyncClient` (same pattern as `read_word_attachment` in `abnt.py`), converts to Markdown via `markitdown`, and truncates to `peca.max_enunciado_chars` with a warning log if truncated.

**Marker for file origin:** To help the LLM distinguish original case content from its own output, the extracted text is wrapped with a marker:

```markdown
### CASO PRÁTICO (extraído do arquivo)

{extracted_markdown}
```

**Combined input:** If both `enunciado` and `arquivo` are provided, the `enunciado` is placed before the file marker as a preamble, forming a single combined user message.

### LLM Call Pattern

Follow the `abnt.py` pattern (single non-streaming call with `await_task_with_heartbeats`):

1. Build messages via `build_peca_messages(enunciado, tipo, area, instrucoes)`.
2. Call `openai_client.chat.completions.create(**build_openai_chat_completion_kwargs(openai_config, messages, stream=False))`.
3. Wrap in `await_task_with_heartbeats(...)`.
4. On success: generate document file → send as attachment.
5. On error: `followup.send(...)` with provider detail.

Why non-streaming: the output is a complete document in a single response. No tool calls, no iterative refinement needed. Streaming adds complexity with no benefit for document generation.

### File Output & Delivery

Reuse the existing document pipeline from `src/helpers/documents.py`:

- DOCX: `DocxProcessor.generate()` — ABNT margins + Times New Roman via `_apply_abnt()`
- ODT: `OdtProcessor.generate()` — pandoc markdown → ODT
- PDF: `PdfProcessor.generate()` — requires pdflatex installed

Filename: `peca_[slug]_[timestamp].[ext]`

Delivery follows the `pesquisa.py` pattern (`send_pesquisa_result` logic, adapted):
- ≤8MB → Discord file attachment
- >8MB → Thread with chunked messages

**PDF note:** pandoc PDF output requires a LaTeX engine (pdflatex). If not installed, the bot returns an error message and suggests using DOCX or ODT. This matches the existing `generate_document` behavior in `src/helpers/documents.py`.

---

## Configuration

```yaml
# config-example.yaml additions
peca:
  max_enunciado_chars: 50000
```

| Key | Default | Purpose |
|-----|---------|---------|
| `peca.max_enunciado_chars` | `50000` | Maximum length of the `enunciado` text before truncation |

Config is hot-reloaded on every invocation via `await asyncio.to_thread(get_config)`. No caching.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `prd/peca.md` | **Create** — this PRD |
| `src/commands/peca.py` | **Create** — slash command registration, input validation, file extraction, LLM orchestration, file delivery |
| `src/prompts/peca.py` | **Create** — `PECA_SYSTEM_PROMPT`, `build_peca_messages()` |
| `src/prompts/__init__.py` | **Edit** — add export for `build_peca_messages` |
| `src/bot.py` | **Edit** — import and call `register_peca_command(...)`; pass `httpx_client` to the command |
| `config-example.yaml` | **Edit** — add `peca:` section |
| `pyproject.toml` | **Edit** — add `markitdown[pdf,docx]` dependency for PDF/DOCX/ODT text extraction |
| `tests/test_peca.py` | **Create** — unit tests for prompt building, validation, and message construction |

---

## Edge Cases & Error Handling

| Case | Behavior |
|------|----------|
| Both `enunciado` empty and `arquivo` not provided | Ephemeral: "Informe um enunciado ou anexe um arquivo (.pdf, .docx, .odt) com o caso." |
| `enunciado` exceeds `peca.max_enunciado_chars` | Truncate (following `abnt.py` pattern), log warning, proceed |
| `arquivo` is not a supported type | Ephemeral: "Tipo de documento não suportado. Envie um arquivo .pdf, .docx ou .odt." |
| `arquivo` read/download fails | Ephemeral: "Não consegui ler o anexo. Verifique se o arquivo é válido." |
| Extracted file text is empty | Ephemeral: "O documento anexado parece estar vazio." |
| Combined `enunciado` + file text exceeds `peca.max_enunciado_chars` | Truncate to limit, log warning, proceed |
| Ambiguous input (no clear legal scenario) | LLM does its best. If the output is incoherent, the user retries with a clearer statement. No server-side validation of "legal sufficiency." |
| User specifies `tipo` that doesn't match the case | LLM follows the `tipo` hint unless it's clearly absurd (e.g., "contestação" in a case without a plaintiff). The system prompt instructs the LLM to prioritize the user's `tipo` but use judgment. |
| `format` is `pdf` but pdflatex is not installed | `generate_document` raises RuntimeError → bot sends the error message with suggestion to use DOCX or ODT |
| LLM API error (APIError) | `followup.send(...)` with provider detail |
| LLM returns empty output | Ephemeral: "Não foi possível gerar a peça processual." |
| LLM returns content_filter | Ephemeral: "A geração foi bloqueada pelo filtro de conteúdo do provedor." |
| LLM invents data (names, CPF, values not in statement) | Post-generation validation is NOT performed by the bot — the system prompt is the guardrail. The user is responsible for reviewing the output. Future enhancement: LLM-as-judge validation pass. |
| File > 8MB | Thread delivery with chunked messages (same pattern as `send_pesquisa_result`) |
| `generate_document` fails | Send raw text in messages instead (same fallback as pesquisa.py) |
| User doesn't have permission | `user_has_permission(...)` check. Ephemeral rejection. |

---

## Example Interaction

```
User:
  /peca enunciado="João alugou um apartamento de Maria em janeiro de 2025.
  O aluguel mensal é de R$ 2.000,00. Em março de 2026, João parou de pagar
  o aluguel. Maria quer ajuizar uma ação de despejo por falta de pagamento.
  O imóvel fica na Comarca de São Paulo."

  tipo=Ação de Despejo
  area=Civil
  format=docx

Bot (ephemeral):
  Gerando a peça processual... Isso pode levar alguns segundos.

Bot (followup):
  Peça processual concluída! Aqui está o documento:
  📎 peca_acao_de_despejo_por_falta_de_pagamento_20260511_143022.docx
```

**Generated document outline:**
```
EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO
DA ___ VARA CÍVEL DA COMARCA DE __________

MARIA [qualificação incompleta — complementar com os
dados faltantes], CPF nº __________, RG nº __________,
residente e domiciliada na __________, por seu advogado
infra-assinado (procuração anexa), OAB/UF nº ________,
vem, respeitosamente, à presença de Vossa Excelência,
propor a presente

AÇÃO DE DESPEJO POR FALTA DE PAGAMENTO C/C COBRANÇA

em face de JOÃO [qualificação incompleta], CPF nº __________,
RG nº __________, residente e domiciliado na __________,
pelos fatos e fundamentos a seguir expostos.

I — DOS FATOS
...

II — DO DIREITO

II.1 — Do Inadimplemento Contratual
...

II.2 — Da Procedência do Pedido de Despejo
...

III — DOS PEDIDOS
1. ...
2. ...
3. ...

IV — DAS PROVAS
...

V — DO VALOR DA CAUSA
Dá-se à causa o valor de R$ XXXX, correspondente a doze
meses de aluguel, nos termos do art. 58, III, da Lei
nº 8.245/1991.

Nestes termos, pede deferimento.
São Paulo, ___ de __________ de 20__.

Advogado(a)
OAB/UF nº ________
```

Note: `R$ XXXX` is used because the annual value depends on how many months of arrears exist (the statement only says "parou de pagar em março de 2026" without specifying the current date or the exact number of unpaid months).

### Example Interaction (File Input)

```
User:
  /peca arquivo=caso_pratico_civil.pdf
        tipo=Petição Inicial
        area=Civil
        format=pdf

Bot (ephemeral):
  Gerando a peça processual... Isso pode levar alguns segundos.

  [Bot downloads caso_pratico_civil.pdf, converts to Markdown via markitdown,
   builds messages, calls LLM, generates PDF output]

Bot (followup):
  Peça processual concluída! Aqui está o documento:
  📄 peca_peticao_inicial_20260511_150530.pdf
```

---

## Testing

Test file: `tests/test_peca.py`

- `test_build_messages_defaults` — only `enunciado`, all optional params default to empty/None, correctly interpolated
- `test_build_messages_all_params` — all 6 parameters injected into messages
- `test_build_messages_tipo_interpolated` — `tipo="Contestação"` appears in system prompt
- `test_build_messages_area_interpolated` — `area="Civil"` appears in system prompt
- `test_build_messages_instrucoes_interpolated` — `instrucoes` appears in system prompt
- `test_build_messages_returns_list_of_dicts` — output is `list[dict]` with role/content keys
- `test_build_messages_enunciado_as_user_message` — user message role contains the raw enunciado
- `test_both_enunciado_and_arquivo_empty_rejected` — empty string + no attachment → validation error
- `test_combined_text_and_file_input` — enunciado + extracted file text concatenated as user message
- `test_format_choices_count` — exactly 3 choices (pdf, docx, odt)
- `test_enunciado_truncated_when_over_max` — input longer than `max_enunciado_chars` is truncated with warning
- `test_build_peca_filename` — filename sanitization + timestamp pattern
- `test_placeholder_present_in_prompt` — system prompt contains placeholder instructions (Processo nº __________)

Fakes follow existing pattern from `tests/test_bot_utils.py` (dataclass-based with `cast()`).

---

## Out of Scope & Future Enhancements

### Out of Scope (v1)

- Google Docs integration
- Multiple provider/thinking model routing (use `state.curr_model` only)
- Web search for jurisprudence enrichment during generation
- Post-generation validation pass (LLM-as-judge checking for invented data)
- Streaming generation
- Interactive refinement via follow-up messages
- Custom citation style beyond ABNT formatting

### Future Enhancements

- Optional web search for relevant jurisprudence to enrich legal reasoning
- Post-generation validation pass: second LLM call to audit the output for invented data
- `/peca` refinement via follow-up replies
- Thinking model routing for complex cases (e.g., constitutional arguments)
- Template library: user can save and reuse piece structures
- Multi-step interactive flow: LLM asks clarifying questions before generating
