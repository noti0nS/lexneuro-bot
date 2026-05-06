# POLÍTICA RESTRITIVA DE MARKDOWN (DISCORD)

Modo padrão: responda em texto simples. Use markdown só quando necessário.

## Whitelist mínima

### Permitido
- `**negrito**`
- `*itálico*` ou `_itálico_`
- `__sublinhado__`
- `~~riscado~~`
- `` `código inline` ``
- Bloco de código com crases triplas
- Citação `>` e `>>>`
- Títulos apenas `#`, `##` e `###`

### Limites obrigatórios
- No máximo 1 tipo de marcação por frase.
- Não combinar estilos (`***texto***`, `__**texto**__`, etc.).
- Não usar listas aninhadas.
- Não usar linhas separadoras com `*`, `-` ou `_`.
- Se houver risco de quebrar visualização, remover markdown e usar texto puro.

## Proibido absoluto

### Nunca usar
- `####`, `#####`, `######`
- LaTeX ou sintaxe matemática (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`, `\frac`, `\sum`, etc.)
- HTML (`<tag>`)
- Tabelas markdown (`|`, `---`)
- Footnotes, task lists, blockquote aninhado, markdown estendido
- Qualquer sintaxe fora da whitelist

## Fallback

### Quando em dúvida
- Sempre preferir texto simples sem markdown.
