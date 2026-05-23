# PRD: Anexos como Fonte — Pipeline Unificado + grep-style Document Tools

## Overview

### Purpose

Extrair texto de anexos (`.pdf`, `.docx`, `.odt`, `.txt`) através de um módulo unificado `src/helpers/attachments.py`, dividir o conteúdo em parágrafos mantidos em memória (`list[str]`), e expor duas ferramentas — `search_document` (grep) e `read_document_chunk` (head/tail) — para que o LLM, durante o loop de pesquisa, inspecione o documento sob demanda. Isso elimina o problema de truncamento/estouro de contexto para documentos longos e consolida as quatro implementações duplicadas de leitura de anexos no código.

Comandos sem tool loop (`/relatorio` sem pesquisa web) continuam injetando o texto diretamente no prompt — o grep é reservado para comandos que já operam com ferramentas (`/pesquisa`, `/jurisprudencia`, e agora `/peca` quando há anexo).

### Target Users

Estudantes e profissionais de direito brasileiros que possuem enunciados, PDFs de editais, ementas, ou textos doutrinários que desejam usar como base para pesquisa acadêmica ou jurisprudencial — sem precisar digitar ou colar manualmente o conteúdo no corpo do comando.

---

## User Flow

```
/pesquisa (com arquivo):
1. User invokes /pesquisa tema="Responsabilidade civil do empregador"
            [anexa enunciado_trabalho.docx]
2. Bot downloads + extracts text via unified reader → splits into paragraph chunks
3. Chunks held in memory as DocumentChunks (list[str], ~payload for tool handler)
4. User message tells LLM: "a document is attached — use search_document
   and read_document_chunk to inspect it"
5. During refinement + research loop, LLM calls search_document(query) to grep
   the document, and read_document_chunk(start, count) to read specific ranges
6. Bot delivers DOCX/ODT file as usual

/jurisprudencia (com arquivo):
1. User invokes /jurisprudencia consulta="Prescrição intercorrente"
            [anexa ementas_stj.pdf] tribunal=stj
2. Same: download → extract → chunk → in memory
3. LLM greps for process numbers, thesis excerpts, then uses those
   as anchors for its web_search calls
4. Bot delivers formatted research results

/peca (com arquivo):
1. User invokes /peca arquivo=caso_pratico.pdf tipo="Petição Inicial"
2. Bot downloads + extracts text → splits into chunks
3. LLM receives document tools + instructions in system prompt
4. LLM greps/searches the document 2-4 times to extract relevant facts,
   parties, legal references, then generates the complete procedural piece
5. Bot delivers PDF/DOCX/ODT file as usual

/peca (sem arquivo): unchanged — enunciado injected directly

/relatorio (refactored, no tool change):
1. Same user flow as before — refactored to use shared reader internally
2. Text is injected into the prompt directly (no tools needed — single LLM call)
```

---

## Slash Command Parameters

### `/pesquisa` — new parameter

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `arquivo` | ATTACHMENT | No | — | Arquivo com enunciado, instruções ou material fonte (.pdf, .docx, .odt, .txt). O conteúdo é extraído, dividido em parágrafos, e o LLM pode consultá-lo sob demanda com `search_document` e `read_document_chunk`. |

Existing parameters unchanged: `tema`, `extensao`, `paginas`, `auto_refinar`, `format`.

### `/jurisprudencia` — new parameter

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `arquivo` | ATTACHMENT | No | — | Arquivo com ementas, acórdãos ou referência doutrinária (.pdf, .docx, .odt, .txt). O LLM usa `search_document` para localizar números de processo, teses, e referências que guiam as buscas web. |

Existing parameters unchanged: `consulta`, `tribunal`, `periodo`, `formato`.

---

## Core Feature Specifications

### 1. Unified Attachment Reader (`src/helpers/attachments.py`)

Consolida validação, download e extração de texto em uma única API, substituindo as implementações dispersas:

| Local atual | Substituído por |
|---|---|
| `documents.py:read_word_attachment()` | Mantido para `/abnt` (extração estrutural `python-docx`/`odfpy` necessária para avaliação ABNT) |
| `peca.py:_extract_file_text()` + `attachment_is_supported()` | `read_attachment_text()` + `attachment_is_supported()` |
| `relatorio.py:_extract_file_text()` + `attachment_is_supported()` | `read_attachment_text()` + `attachment_is_supported()` |
| `documents.py:attachment_is_supported_word_document()` | Mantido para `/abnt` |

**API pública:**

```python
# src/helpers/attachments.py

SUPPORTED_CONTENT_TYPES: tuple[str, ...] = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
)

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx", ".odt", ".txt")


def attachment_is_supported(attachment: discord.Attachment) -> bool:
    """Check content type AND filename extension."""


async def read_attachment_text(
    attachment: discord.Attachment,
    http_client: httpx.AsyncClient,
) -> str:
    """Download and extract full text from a supported attachment.
    Uses markitdown for .pdf/.docx/.odt, raw decode for .txt.
    Returns full text (no truncation — caller decides what to do).
    Raises ValueError if attachment type is unsupported.
    Raises httpx.HTTPError on download failure.
    """
```

**Extraction strategy per format:**

| Extensão | Método | Biblioteca |
|----------|--------|-----------|
| `.pdf` | `MarkItDown().convert_stream()` | `markitdown[pdf]` |
| `.docx` | `MarkItDown().convert_stream()` | `markitdown[docx]` |
| `.odt` | `MarkItDown().convert_stream()` | `markitdown` (built-in) |
| `.txt` | `bytes.decode("utf-8", errors="replace")` | stdlib |

### 2. DocumentChunks — In-Memory Paragraph Store

Nada de SQLite. O texto extraído é dividido em parágrafos e mantido em uma estrutura simples na memória do processo:

```python
# src/helpers/attachments.py (same module — it's small enough)

from dataclasses import dataclass, field

@dataclass
class DocumentChunks:
    """Paragraph-level chunks of an extracted document, held in memory."""
    filename: str
    chunks: list[str]             # one paragraph per element (split on \n\n)
    total_chunks: int = 0         # computed in __post_init__
    total_chars: int = 0          # computed in __post_init__

    def __post_init__(self) -> None:
        self.total_chunks = len(self.chunks)
        self.total_chars = sum(len(c) for c in self.chunks)


def build_document_chunks(filename: str, full_text: str) -> DocumentChunks:
    """Split extracted text into paragraph chunks.
    Filters empty paragraphs. No truncation — unlimited size."""
    raw_chunks = [p.strip() for p in full_text.split("\n\n")]
    chunks = [c for c in raw_chunks if c]
    return DocumentChunks(filename=filename, chunks=chunks)
```

**Chunking rules:**
- Split on `\n\n` (paragraph boundaries — `markitdown` uses double-newline for paragraph breaks)
- Strip whitespace from each chunk
- Discard empty chunks (blank lines between paragraphs)
- No per-chunk size limit — a very long paragraph stays as one chunk
- No overall size limit — 500K chars of extracted text is just a `list[str]` with hundreds of entries

**Memory considerations:**
- 500K chars ~= 0.5 MB of Python strings — negligible
- A 5 MB PDF that extracts to 200K words ~= 1.2 MB of strings — still negligible
- Chunks live only for the duration of the command (created at extraction, GC'd when the handler returns)
- No persistence, no cleanup, no disk I/O

### 3. grep-style Document Tools for the Research Loop

Duas ferramentas simples, análogas a `grep` e `head`/`tail`, adicionadas ao conjunto de ferramentas do research loop quando há um anexo.

#### 3a. `search_document` — grep

```python
SEARCH_DOCUMENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_document",
        "description": (
            "Search the user's uploaded document for keywords or phrases. "
            "Case-insensitive substring matching across all paragraphs. "
            "Optionally include surrounding paragraphs for context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to search for (case-insensitive substring match).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matching chunks to return (default 5, max 10).",
                },
                "context_before": {
                    "type": "integer",
                    "description": "Number of paragraphs BEFORE each match to include (default 0).",
                },
                "context_after": {
                    "type": "integer",
                    "description": "Number of paragraphs AFTER each match to include (default 0).",
                },
            },
            "required": ["query"],
        },
    },
}
```

**Handler:**

```python
def handle_search_document(doc: DocumentChunks, args: dict[str, Any]) -> str:
    query = args["query"].lower()
    max_results = min(args.get("max_results", 5), 10)
    ctx_before = max(args.get("context_before", 0), 0)
    ctx_after = max(args.get("context_after", 0), 0)

    hits: list[dict[str, Any]] = []
    for i, chunk in enumerate(doc.chunks):
        if query in chunk.lower():
            start = max(0, i - ctx_before)
            end = min(doc.total_chunks, i + ctx_after + 1)
            context_chunks = [
                {"chunk_index": j, "chunk_text": doc.chunks[j][:2000]}
                for j in range(start, end)
            ]
            hits.append({"match_index": i, "context": context_chunks})
            if len(hits) >= max_results:
                break

    if not hits:
        return json.dumps(
            {"message": f'No paragraphs matched "{args["query"]}". Try a different keyword.'},
            ensure_ascii=False,
        )

    return json.dumps(hits, ensure_ascii=False, default=str)
```

**Example LLM calls:**

| Intenção | Tool call |
|----------|-----------|
| Find mentions of a specific law article | `search_document(query="art. 319", max_results=5)` |
| Find references with surrounding context | `search_document(query="prescrição", max_results=3, context_before=1, context_after=1)` |
| Find process numbers | `search_document(query="REsp", max_results=5, context_after=1)` |

#### 3b. `read_document_chunk` — head/tail/range

```python
READ_DOCUMENT_CHUNK_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_document_chunk",
        "description": (
            "Read a specific range of paragraphs from the user's uploaded document "
            "by chunk index. Use this to scan sections, read the beginning or end, "
            "or follow up on search_document results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_index": {
                    "type": "integer",
                    "description": "First chunk index to read (0-based).",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of chunks to read (default 5, max 10).",
                },
            },
            "required": ["start_index"],
        },
    },
}
```

**Handler:**

```python
def handle_read_document_chunk(doc: DocumentChunks, args: dict[str, Any]) -> str:
    start = max(args["start_index"], 0)
    count = min(args.get("count", 5), 10)
    end = min(doc.total_chunks, start + count)

    if start >= doc.total_chunks:
        return json.dumps(
            {"message": f"Start index {start} is out of range. Document has {doc.total_chunks} chunks."},
            ensure_ascii=False,
        )

    chunks = [
        {"chunk_index": i, "chunk_text": doc.chunks[i][:2000]}
        for i in range(start, end)
    ]

    return json.dumps(chunks, ensure_ascii=False, default=str)
```

**Example LLM calls:**

| Intenção | Tool call |
|----------|-----------|
| Read the beginning of the document | `read_document_chunk(start_index=0, count=5)` |
| Read the conclusion section | `read_document_chunk(start_index=85, count=10)` |
| Follow up on a search hit at chunk 34 | `read_document_chunk(start_index=34, count=3)` |

#### 3c. Tool definitions (shared constant)

```python
# src/helpers/ai_tools.py (or src/helpers/attachments.py)

DOCUMENT_TOOLS: list[dict[str, Any]] = [
    SEARCH_DOCUMENT_TOOL,
    READ_DOCUMENT_CHUNK_TOOL,
]
```

#### 3d. Simple tool loop for single-call commands (`/peca`)

`/peca` não usa `run_research_loop()` — faz uma única chamada `execute_chat_completion()` sem ferramentas. Para integrar as document tools sem reescrever o comando, envolvemos a chamada em um mini tool loop no próprio `peca.py`:

```python
# Dentro de peca_command, quando arquivo foi fornecido:

messages = build_peca_messages(
    enunciado=combined_text,
    tipo=tipo, area=area, instrucoes=instrucoes,
    has_attachment=True,
)

doc = build_document_chunks(attachment.filename, extracted_text)

def handle_tool(tool_name, args):
    if tool_name == "search_document":
        return handle_search_document(doc, args)
    if tool_name == "read_document_chunk":
        return handle_read_document_chunk(doc, args)
    return json.dumps({"error": f"Unknown tool: {tool_name}"})

# Mini loop: cap at 5 iterations (document inspection only, no web search)
for _ in range(5):
    completion = await execute_chat_completion(
        config=state.config,
        model_name=curr_model,
        messages=messages,
        tools=DOCUMENT_TOOLS,
        tool_choice="auto",
    )
    choice = completion.choices[0]
    if choice.finish_reason != "tool_calls":
        raw_output = get_completion_text(completion)
        break

    messages.append(choice.message.to_dict())
    for tc in choice.message.tool_calls:
        args = json.loads(tc.function.arguments)
        result = handle_tool(tc.function.name, args)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })
else:
    # Exhausted: force final call without tools
    completion = await execute_chat_completion(
        config=state.config,
        model_name=curr_model,
        messages=messages,
        tool_choice="none",
    )
    raw_output = get_completion_text(completion)
```

O mini loop é auto-contido — nenhuma mudança no `execute_chat_completion()` ou em helpers compartilhados. Quando não há arquivo, o fluxo existente (single call sem tools) permanece inalterado.

### 4. Integrating Tools into the Research Loop

`run_research_loop()` in `src/helpers/ai_tools.py` is extended to accept extra tools via a callback:

**Current signature:**
```python
async def run_research_loop(
    config, model_name, messages, *,
    max_iterations, search_results_per_topic, max_page_fetches,
    reasoning_effort=None, user_id=None,
) -> str:
```

**New signature:**
```python
async def run_research_loop(
    config, model_name, messages, *,
    max_iterations, search_results_per_topic, max_page_fetches,
    reasoning_effort=None, user_id=None,
    extra_tools: list[dict[str, Any]] | None = None,
    on_extra_tool: Callable[[str, dict[str, Any]], str] | None = None,
) -> str:
```

- `extra_tools`: appended to the default `[web_search, fetch_page]` tool set
- `on_extra_tool(tool_name, args) -> str`: synchronous callback invoked when the LLM calls a non-standard tool. Returns the tool result as a JSON string.

**How `/pesquisa` wires it up:**

```python
# Inside pesquisa_command handler, after extracting the file:

doc: DocumentChunks | None = None
extra_tools: list[dict[str, Any]] | None = None
on_extra_tool = None

if attachment:
    text = await read_attachment_text(attachment, httpx_client)
    doc = build_document_chunks(attachment.filename, text)
    extra_tools = DOCUMENT_TOOLS

    def handle_tool(tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "search_document":
            return handle_search_document(doc, args)
        if tool_name == "read_document_chunk":
            return handle_read_document_chunk(doc, args)
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    on_extra_tool = handle_tool

raw_output = await run_research_loop(
    ...,
    extra_tools=extra_tools,
    on_extra_tool=on_extra_tool,
)
# doc goes out of scope here → GC collects the list[str]
```

### 5. Prompt Changes

#### `/pesquisa` — `src/prompts/pesquisa.py`

System prompt gains a conditional section when `has_attachment=True`. The file text does NOT go in the user message:

```python
DOCUMENT_TOOL_SECTION = """
### DOCUMENTO DO USUÁRIO
O usuário anexou um documento como fonte primária para esta pesquisa.
O conteúdo NÃO está nesta mensagem — use as ferramentas abaixo para consultá-lo:

- `search_document(query, max_results, context_before, context_after)`: busca
  palavras-chave ou frases no documento (case-insensitive). Use context_before/after
  para ver parágrafos vizinhos.
- `read_document_chunk(start_index, count)`: lê parágrafos específicos por índice
  (0-based). Use para ler o início, o fim, ou expandir um trecho encontrado.

IMPORTANTE: O documento é sua fonte PRIMÁRIA. Se houver conflito entre a pesquisa
web e o documento, o documento prevalece. Inspecione o documento ANTES de fazer
buscas web — os termos e referências contidos nele devem guiar suas queries.
"""

def build_pesquisa_messages(
    *,
    tema: str,
    extensao: str = "padrao",
    paginas: int = 3,
    has_attachment: bool = False,
) -> list[dict[str, Any]]:
    system_prompt = PESQUISA_SYSTEM_PROMPT.format(...)
    if has_attachment:
        system_prompt += "\n\n" + DOCUMENT_TOOL_SECTION

    user_message = f"Tema da pesquisa: {tema}\n\n..."
    return [
        dict(role="system", content=system_prompt),
        dict(role="user", content=user_message),
    ]
```

#### `/jurisprudencia` — `src/prompts/jurisprudencia.py`

Mesmo padrão:

```python
JURIS_DOCUMENT_TOOL_SECTION = """
### DOCUMENTO DE REFERÊNCIA
O usuário anexou um documento (ementas, acórdãos, doutrina) como referência.
Use `search_document` para extrair números de processo, teses e citações.
Use `read_document_chunk` para ler trechos específicos.
Use esses achados como base para suas buscas web — os números de processo e
termos jurídicos do documento devem direcionar suas queries.
"""

def build_jurisprudencia_messages(
    *,
    consulta: str,
    tribunal: str = "todos",
    periodo: str | None = None,
    has_attachment: bool = False,
) -> list[dict[str, Any]]:
    ...
```

#### `/peca` — `src/prompts/peca.py`

Quando `has_attachment=True`, o system prompt ganha uma seção instruindo o LLM a usar as ferramentas de documento. O texto do arquivo NÃO vai no user message (ao contrário do comportamento atual, que injeta via `CASO PRÁTICO (extraído do arquivo)`):

```python
PECA_DOCUMENT_TOOL_SECTION = """
### CASO PRÁTICO (documento anexado)
O usuário anexou um arquivo com o enunciado do caso prático.
O conteúdo NÃO está nesta mensagem — use as ferramentas abaixo para consultá-lo:

- `search_document(query, max_results, context_before, context_after)`: busca
  palavras-chave no documento. Use para localizar: nomes das partes, fatos
  relevantes, artigos de lei citados, valores, datas, cláusulas contratuais.
- `read_document_chunk(start_index, count)`: lê parágrafos específicos.
  Use para ler a descrição completa do caso, qualificação das partes,
  ou pedidos mencionados no enunciado.

IMPORTANTE: Inspecione o documento ANTES de redigir a peça. Extraia dele:
- Quem é o autor e quem é o réu (qualificação)
- Os fatos juridicamente relevantes (cronologia, valores, descumprimentos)
- A área do direito e o tipo de peça (se não informados explicitamente)
- Fundamentos legais mencionados no próprio enunciado
"""

def build_peca_messages(
    *,
    enunciado: str,
    tipo: str | None = None,
    area: str | None = None,
    instrucoes: str | None = None,
    has_attachment: bool = False,
) -> list[dict[str, Any]]:
    system_prompt = PECA_SYSTEM_PROMPT.format(...)
    if has_attachment:
        system_prompt += "\n\n" + PECA_DOCUMENT_TOOL_SECTION

    user_message = enunciado  # apenas o texto do enunciado, sem o conteúdo do arquivo
    return [
        dict(role="system", content=system_prompt),
        dict(role="user", content=user_message),
    ]
```

**Nota sobre o `combined_text`:** Quando o usuário fornece tanto `enunciado` quanto `arquivo`, o `combined_text` (enunciado + marcador + texto extraído) deixa de existir. Apenas o `enunciado` vai no user message. O conteúdo do arquivo é acessado exclusivamente via ferramentas.

**`/relatorio` — sem alteração nos prompts**

### 6. LLM Call Pattern (per command)

| Command | File handling | Tool set |
|---------|-------------|----------|
| `/pesquisa` sem arquivo | — | `web_search` + `fetch_page` |
| `/pesquisa` com arquivo | Extract → `build_document_chunks()` → `doc` in closure | `web_search` + `fetch_page` + `search_document` + `read_document_chunk` |
| `/jurisprudencia` sem arquivo | — | `web_search` + `fetch_page` |
| `/jurisprudencia` com arquivo | Extract → `build_document_chunks()` → `doc` in closure | same as pesquisa with file |
| `/relatorio` com arquivo, sem pesquisa | Extract → inject into prompt | Nenhuma (single call) |
| `/relatorio` com arquivo, com pesquisa | Extract → `build_document_chunks()` → `doc` in closure | `web_search` + `fetch_page` + `search_document` + `read_document_chunk` |
| `/peca` sem arquivo | — | Nenhuma (single call) |
| `/peca` com arquivo | Extract → `build_document_chunks()` → `doc` in closure | Mini tool loop (max 5 iter): `search_document` + `read_document_chunk` |
| `/abnt` | Extract via `documents.py` → inject into prompt | Nenhuma (single call) |

### 7. Refactoring Existing Commands

**`/peca`** (`src/commands/slashes/peca.py`):
- Replace `_extract_file_text()` and `attachment_is_supported()` with imports from `src/helpers/attachments.py`
- Remove local `SUPPORTED_INPUT_CONTENT_TYPES`, `SUPPORTED_INPUT_EXTENSIONS`, `FILE_MARKER`
- Remove `combined_text` + file marker injection logic — file content goes to `DocumentChunks`, not into prompt
- When `arquivo` provided: `build_document_chunks()` → mini tool loop (max 5 iter) with `DOCUMENT_TOOLS`
- When `arquivo` NOT provided: single `execute_chat_completion()` without tools (unchanged flow)

**`/relatorio`** (`src/commands/slashes/relatorio.py`):
- Replace `_extract_file_text()` and `attachment_is_supported()` with imports from `src/helpers/attachments.py`
- Remove local `SUPPORTED_INPUT_CONTENT_TYPES`, `SUPPORTED_INPUT_EXTENSIONS`
- Com `pesquisar=False`: injeta texto no prompt
- Com `pesquisar=True` e arquivo: usa `DocumentChunks` + ferramentas

**`/abnt`** (`src/commands/slashes/abnt.py`):
- Sem alteração

**`/sql_cmd`, `/json_cmd`, `lex!capture`:**
- Sem alteração

### 8. Model Resolution & Performance

- Extração via `markitdown` roda em `asyncio.to_thread()` (CPU-bound)
- Handlers `handle_search_document` e `handle_read_document_chunk` são síncronos e O(n) — iteração linear sobre a lista de chunks. Para ~500 chunks (documento grande), leva <1ms. Sem necessidade de `asyncio.to_thread()`.
- Sem I/O de disco, sem conexão de banco, sem cleanup
- `DocumentChunks` vive no closure da função handler. Quando o handler retorna, o GC coleta.

---

## Configuration

```yaml
# config-example.yaml additions / changes

pesquisa:
  max_tool_iterations: 15
  search_results_per_topic: 8
  max_page_fetches: 5
  model: deepseek/deepseek-r1
  # sem max_fonte_chars — in-memory chunks lidam com qualquer tamanho

jurisprudencia:
  max_search_iterations: 12
  search_results_per_query: 8
  max_page_fetches: 5
  # sem max_fonte_chars

# peca, relatorio keys unchanged
```

Nenhuma seção de configuração nova é necessária. Os limites (`max_results=10`, `context max`, `chunk_text[:2000]`) são constantes sensatas que não precisam de configuração.

Config is hot-reloaded on every invocation via `await asyncio.to_thread(get_config)`. No caching.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `prd/anexos.md` | **Edit** — this PRD |
| `src/helpers/attachments.py` | **Create** — `attachment_is_supported()`, `read_attachment_text()`, `DocumentChunks`, `build_document_chunks()`, `handle_search_document()`, `handle_read_document_chunk()`, tool definitions, shared constants |
| `src/helpers/ai_tools.py` | **Edit** — extend `run_research_loop()` signature with `extra_tools` + `on_extra_tool` callback; dispatch extra tools in the tool-calling loop |
| `src/commands/slashes/pesquisa.py` | **Edit** — add `arquivo` param; import from `attachments.py`; download → extract → `build_document_chunks()`; pass `DOCUMENT_TOOLS` + handler callback to `run_research_loop()` |
| `src/commands/slashes/jurisprudencia.py` | **Edit** — add `arquivo` param; same pattern as pesquisa; accept `httpx_client` |
| `src/commands/slashes/peca.py` | **Edit** — replace `_extract_file_text()` and `attachment_is_supported()` with imports from `attachments.py`; remove local constants + `FILE_MARKER`; when arquivo: `build_document_chunks()` + mini tool loop (max 5 iter) with `DOCUMENT_TOOLS`; remove `combined_text` injection logic |
| `src/commands/slashes/relatorio.py` | **Edit** — replace `_extract_file_text()` and `attachment_is_supported()` with imports from `attachments.py`; when `pesquisar=True` + arquivo, use `DocumentChunks` + tools path |
| `src/prompts/pesquisa.py` | **Edit** — change `fonte_arquivo` param to `has_attachment: bool`; inject `DOCUMENT_TOOL_SECTION` into system prompt when True; remove file text from user message |
| `src/prompts/jurisprudencia.py` | **Edit** — change `fonte_arquivo` param to `has_attachment: bool`; inject `JURIS_DOCUMENT_TOOL_SECTION` into system prompt when True |
| `src/prompts/peca.py` | **Edit** — add `has_attachment` param to `build_peca_messages()`; inject `PECA_DOCUMENT_TOOL_SECTION` into system prompt when True; remove `FILE_MARKER` + file content injection from user message |
| `src/prompts/__init__.py` | **Edit** — update exports if signatures change |
| `src/bot.py` | **Edit** — pass `httpx_client` to `register_jurisprudencia_command()` |
| `pyproject.toml` | **No change** — `markitdown[pdf,docx]` already present; no new deps |
| `tests/test_attachments.py` | **Create** — unit tests for reader, chunk builder, search handler, read handler |
| `tests/test_pesquisa.py` | **Edit** — update tests for `has_attachment` parameter; test `DOCUMENT_TOOL_SECTION` injection |
| `tests/test_jurisprudencia.py` | **Edit** — update tests for `has_attachment` parameter |

---

## Edge Cases & Error Handling

| Case | Behavior |
|------|----------|
| `arquivo` is not a supported type (.pdf, .docx, .odt, .txt) | Ephemeral: "Tipo de arquivo não suportado. Envie .pdf, .docx, .odt ou .txt." |
| `arquivo` provided but download fails (HTTP error, timeout) | Ephemeral: "Não consegui baixar o arquivo. Tente novamente." Log exception. |
| `arquivo` provided but extraction fails (corrupt file) | Ephemeral: "Não consegui extrair o texto do arquivo. Verifique se ele é válido." Log exception. |
| Extracted text is empty / whitespace-only | Ephemeral: "O arquivo anexado parece estar vazio." |
| Document is very large (500K+ chars, 1000+ chunks) | All chunks in memory. grep is linear O(n) — still <5ms for 1000 chunks. No context window pressure. |
| `search_document` finds no matches | Returns `{"message": "No paragraphs matched..."}`. LLM can retry with different keyword. |
| `search_document` finds 50 matches but `max_results=5` | Returns first 5 hits only. LLM can paginate with narrower queries or use `read_document_chunk` to scan. |
| `read_document_chunk` with `start_index` beyond document end | Returns `{"message": "Start index X is out of range..."}`. LLM adjusts. |
| Context window: per-chunk `chunk_text` limited to 2000 chars | Long paragraphs are truncated in tool output. LLM can use `read_document_chunk` to read the full chunk if needed (single-chunk reads still truncate at 2000 — document length is unlimited but each tool response is bounded). |
| Both `tema`/`consulta` and `arquivo` are empty | Existing validation catches this (tema/consulta required fields). |
| `/pesquisa` with `arquivo` + `auto_refinar=True` | Refinement phase has `tool_choice="none"` — the document tools are NOT available. The LLM is told about the document in the prompt but inspects it during the research phase. |
| `/peca` with `arquivo`, mini tool loop exhausts (5 iter) | Force final call with `tool_choice="none"` — LLM generates with whatever it has already inspected. Log warning. |
| `/peca` with `arquivo` but `enunciado` also provided | `enunciado` goes in user message as preamble. Document tools inspect the file content. No `combined_text` — LLM greps the file for details that complement the enunciado. |
| `/peca` with `arquivo`, LLM doesn't call any document tool | Mini loop: first call returns `finish_reason="stop"` immediately. Document was never inspected — LLM may provide a weaker peça. Accept and proceed (same as `/pesquisa` accepting a doc without searching). |
| Large PDF with embedded images (scanned document) | `markitdown` may produce little/no text. `build_document_chunks` produces few chunks. `search_document` returns few/no matches → LLM informed. |
| `arquivo` is `.txt` with non-UTF-8 encoding | `bytes.decode("utf-8", errors="replace")` — replaces invalid sequences. |
| Permission denied | Ephemeral rejection BEFORE any file download. |
| Provider error during LLM call (APIError) | Followup with provider detail — unchanged. |
| Content filter triggered | Ephemeral error — unchanged. |
| `generate_document` fails | Fallback to raw text in messages — unchanged. |

---

## Example Interaction

### `/pesquisa` with attachment

```
User:
  /pesquisa tema="Responsabilidade civil do empregador"
            extensao="Padrão (~3 págs. / 1.500w)"
            [uploads enunciado_direito_civil.pdf]

Bot (ephemeral):
  Pesquisando e gerando o documento... Isso pode levar alguns minutos.

  [Downloads PDF, extracts 12.430 chars via markitdown]
  [Splits into 48 paragraph chunks → DocumentChunks in memory]
  [Builds messages with DOCUMENT_TOOL_SECTION in system prompt]

  [Refinement phase: LLM thinks about the topic. No tool calls yet.]

  [Research loop iteration 1 — LLM scouts the document:]
  LLM → search_document(query="artigo", max_results=5, context_after=0)
  Tool → [{match_index: 3, context: [{chunk_index: 3, chunk_text: "...Art. 7º, XXVIII da CF/88..."}]},
           {match_index: 12, context: [{chunk_index: 12, chunk_text: "...arts. 186 e 927 do CC..."}]}]

  [Research loop iteration 2 — LLM reads the case section:]
  LLM → read_document_chunk(start_index=20, count=10)
  Tool → [{chunk_index: 20, chunk_text: "João da Silva, operário..."}, ...]

  [Research loop iteration 3 — LLM searches web with document anchors:]
  LLM → web_search("responsabilidade civil acidente trabalho art. 7 XXVIII CF")
  Tool → 8 DuckDuckGo results

  [Research loop iteration 4:]
  LLM → search_document(query="risco", max_results=3, context_before=1, context_after=1)
  Tool → 2 hits discussing "teoria do risco" in the document

  [Research loop iteration 5:]
  LLM → web_search("teoria do risco atividade CLT acidente trabalho")
  LLM → fetch_page("https://jusbrasil.com.br/artigos/...")

  [Research loop iteration 6:]
  LLM → finish_reason="stop", generates 3-page ABNT DOCX
       citing both the source document quotes and web findings

Bot (followup):
  Pesquisa concluída! Aqui está o documento:
  📘 pesquisa_responsabilidade_civil_do_empregador_20260521_143022.docx
```

### `/jurisprudencia` with attachment

```
User:
  /jurisprudencia consulta="Prescrição intercorrente na execução fiscal"
                  tribunal="STJ — Superior Tribunal de Justiça"
                  periodo="2020-2025"
                  [uploads ementas_relevantes.docx]

Bot (ephemeral):
  Buscando jurisprudência... Isso pode levar alguns minutos.

  [Downloads DOCX, extracts 8.721 chars → 35 paragraphs → DocumentChunks]

  [Research loop iteration 1:]
  LLM → search_document(query="REsp", max_results=5, context_after=1)
  Tool → [{match_index: 2, context: [
            {chunk_index: 2, chunk_text: "...REsp 1.340.553/RS..."},
            {chunk_index: 3, chunk_text: "...Relator: Min. Mauro Campbell..."}
          ]},
          {match_index: 7, context: [...]}]

  [Research loop iteration 2:]
  LLM → web_search("REsp 1.340.553 prescrição intercorrente STJ")
  Tool → finds STJ decision page

  [Research loop iteration 3:]
  LLM → fetch_page("https://stj.jus.br/...")
  Tool → full ementa from STJ portal

  [Research loop iteration 4:]
  LLM → search_document(query="tema", max_results=5)
  Tool → 3 hits mentioning "Tema 566", "Tema 567"

  [Research loop iteration 5:]
  LLM → read_document_chunk(start_index=0, count=5)
  Tool → reads the document header/introduction for context

  [Research loop iteration 6:]
  LLM → finish_reason="stop", generates research with
       side-by-side comparison of doc citations vs STJ portal results

Bot (followup):
  Pesquisa de jurisprudência concluída! Aqui está o documento:
  📘 jurisprudencia_prescricao_intercorrente_na_execucao_fiscal_20260521_150530.docx
```

### `/peca` with attachment

```
User:
  /peca enunciado="João alugou um apartamento de Maria em janeiro de 2025."
         tipo="Ação de Despejo"
         area="Civil"
         [uploads contrato_locacao.pdf]

Bot (ephemeral):
  Gerando a peça processual... Isso pode levar alguns segundos.

  [Downloads PDF, extracts text via markitdown → 22 paragraphs → DocumentChunks]
  [Builds messages with PECA_DOCUMENT_TOOL_SECTION in system prompt]
  [User message: only "João alugou um apartamento de Maria em janeiro de 2025."]

  [Mini loop iteration 1 — LLM scouts the document:]
  LLM → search_document(query="aluguel", max_results=5, context_after=2)
  Tool → [{match_index: 4, context: [
            {chunk_index: 4, chunk_text: "...aluguel mensal de R$ 2.000,00..."},
            {chunk_index: 5, chunk_text: "...pagamento até o dia 10 de cada mês..."},
            {chunk_index: 6, chunk_text: "...cláusula quarta: multa de 10% em caso de atraso..."}
          ]}]

  [Mini loop iteration 2 — LLM reads the contract details:]
  LLM → read_document_chunk(start_index=0, count=8)
  Tool → [{chunk_index: 0, chunk_text: "CONTRATO DE LOCAÇÃO RESIDENCIAL..."},
           {chunk_index: 1, chunk_text: "LOCADORA: Maria da Silva, CPF..."},
           {chunk_index: 2, chunk_text: "LOCATÁRIO: João Pereira, CPF..."},
           ...]

  [Mini loop iteration 3 — LLM finds relevant clauses:]
  LLM → search_document(query="rescisão", max_results=3, context_before=1, context_after=2)
  Tool → [{match_index: 14, context: [
            {chunk_index: 13, chunk_text: "...prazo de 30 meses, iniciando em 01/01/2025..."},
            {chunk_index: 14, chunk_text: "...cláusula décima: rescisão por falta de pagamento..."},
            {chunk_index: 15, chunk_text: "...notificação extrajudicial com prazo de 15 dias..."},
            {chunk_index: 16, chunk_text: "...art. 9º da Lei 8.245/1991 (Lei do Inquilinato)..."}
          ]}]

  [Mini loop iteration 4:]
  LLM → finish_reason="stop", generates complete Ação de Despejo
       with qualification extracted from the contract PDF, legal foundation
       citing the exact clauses and lei references found in the document

Bot (followup):
  Peça processual concluída! Aqui está o documento:
  📘 peca_acao_de_despejo_20260521_150530.docx
```

Note how the LLM no longer invents placeholders (`CPF nº __________`, `Comarca de __________`) for data present in the document. By grepping the contract, it extracts `Maria da Silva, CPF...`, `João Pereira, CPF...`, `R$ 2.000,00`, etc. — producing a more complete peça with fewer blanks.

---

## Testing

### Test file: `tests/test_attachments.py`

**Reader tests:**
- `test_attachment_is_supported_valid_pdf` — PDF content type → True
- `test_attachment_is_supported_valid_docx` — DOCX → True
- `test_attachment_is_supported_valid_odt` — ODT → True
- `test_attachment_is_supported_valid_txt` — TXT → True
- `test_attachment_is_supported_extension_fallback` — Unknown content type but .pdf extension → True
- `test_attachment_is_supported_rejects_zip` — ZIP → False
- `test_attachment_is_supported_rejects_image` — image/png → False
- `test_attachment_is_supported_empty_no_extension` — No type, no extension → False

**Chunk builder tests:**
- `test_build_document_chunks_splits_paragraphs` — Text with `\n\n` → multiple chunks
- `test_build_document_chunks_filters_empty` — Consecutive `\n\n\n` → no empty chunks
- `test_build_document_chunks_single_paragraph` — No `\n\n` → single chunk
- `test_build_document_chunks_total_chunks` — `total_chunks` matches `len(chunks)`
- `test_build_document_chunks_total_chars` — `total_chars` matches sum of lengths
- `test_build_document_chunks_empty_text` — Empty string → 0 chunks

**search_document tests:**
- `test_search_document_exact_match` — Exact keyword → returns matching chunks
- `test_search_document_case_insensitive` — "REsp" matches "resp" and "RESP"
- `test_search_document_no_match` — Non-existent keyword → empty message
- `test_search_document_max_results` — 50 matches but `max_results=5` → returns 5
- `test_search_document_context_before` — Hit at index 10, `context_before=1` → includes chunk 9
- `test_search_document_context_after` — Hit at index 10, `context_after=2` → includes chunks 11,12
- `test_search_document_context_clamped` — Hit at index 0, `context_before=3` → starts at 0 (no negative index)
- `test_search_document_chunk_text_truncated` — Chunk > 2000 chars → truncated in output

**read_document_chunk tests:**
- `test_read_document_chunk_first_chunks` — `start=0, count=3` → returns chunks 0,1,2
- `test_read_document_chunk_middle_range` — `start=10, count=5` → returns chunks 10-14
- `test_read_document_chunk_clamped_end` — `start=45, count=10` with 48 chunks → returns 45-47
- `test_read_document_chunk_out_of_range` — `start=100` with 48 chunks → error message
- `test_read_document_chunk_default_count` — `count` omitted → defaults to 5
- `test_read_document_chunk_max_count` — `count=50` → clamped to 10

### Test file: `tests/test_pesquisa.py` (changes)

- `test_build_messages_has_attachment_true` — `has_attachment=True` injects `DOCUMENT_TOOL_SECTION`
- `test_build_messages_has_attachment_false` — No section when False
- `test_build_messages_no_file_text_in_user_message` — User message does NOT contain extracted text

### Test file: `tests/test_jurisprudencia.py` (changes)

- `test_build_messages_has_attachment_true` — `has_attachment=True` injects `JURIS_DOCUMENT_TOOL_SECTION`
- `test_build_messages_has_attachment_false` — No section when False
- `test_build_messages_no_file_text_in_user_message` — User message does NOT contain extracted text

### Test file: `tests/test_peca.py` (changes)

- `test_build_messages_has_attachment_true` — `has_attachment=True` injects `PECA_DOCUMENT_TOOL_SECTION` into system prompt
- `test_build_messages_has_attachment_false` — No `PECA_DOCUMENT_TOOL_SECTION` when False
- `test_build_messages_no_file_text_in_user_message` — User message contains only `enunciado`, not the extracted file text
- `test_build_messages_no_file_marker` — No `CASO PRÁTICO (extraído do arquivo)` marker when has_attachment=True (the marker is removed)
- `test_build_messages_enunciado_and_attachment` — `enunciado` goes in user message, file tools section in system prompt, no `combined_text`

### Test file: `tests/test_ai_tools.py` (additions)

- `test_run_research_loop_with_extra_tools` — Extra tools passed; callback invoked on matching tool name
- `test_run_research_loop_without_extra_tools` — Loop works without extra_tools (backward compat)

Fakes follow existing pattern from `tests/test_bot_utils.py` (dataclass-based with `cast()`).

---

## Out of Scope & Future Enhancements

### Out of Scope (v1)

- **PDF OCR** — scanned/image-based PDFs. OCR integration is separate.
- **Multiple file uploads** — um `arquivo` por invocação.
- **Regex search** — `search_document` usa substring matching. Regex pode ser adicionado como parâmetro opcional no futuro.
- **Streaming extraction progress** — `markitdown` é síncrono. Sem progress reporting.
- **Attachment support in AI chat (`on_message`)** — o handler `on_message` em `bot.py` continua aceitando apenas `text/*` e `image/*`.
- **Refactoring `/abnt`** — precisa de parsing estrutural `python-docx`/`odfpy`.
- **Document tools durante a fase de refinement do `/pesquisa`** — refinement usa `tool_choice="none"`.
- **FTS / BM25 / embeddings** — substring matching é suficiente para v1. Não há dependências externas.
- **SQLite** — testado e descartado como overengineered para este caso de uso.

### Future Enhancements (v2+)

- **Regex mode**: `search_document(query="art\. \d+", regex=True)` para buscas por padrão.
- **Semantic search via embeddings**: Para documentos muito longos (>2000 chunks), gerar embeddings e permitir busca por similaridade.
- **Attachment support in `on_message` AI chat**: `DocumentChunks` + mesmas ferramentas para mensagens regulares.
- **Multiple file uploads**: Um `DocumentChunks` por arquivo, `search_document` ganha param `file_label`.
- **OCR fallback**: Se `markitdown` retornar texto vazio, tentar OCR.
- **Progress heartbeat durante extração**: Logs periódicos para arquivos >5MB.
