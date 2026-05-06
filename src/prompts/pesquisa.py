from typing import Any

from .abnt import load_abnt_reference

CONTEXTO_LABELS: dict[str, str] = {
    "academico": "Acadêmico / ABNT",
    "npj": "NPJ / Peça Jurídica",
    "programacao": "Programação / Neuro",
}

EXTENSAO_LABELS: dict[str, str] = {
    "curto": "Direto ao Ponto (~1 pág. / 500 palavras)",
    "padrao": "Padrão (~3 págs. / 1.500 palavras)",
    "completo": "Dossiê Completo (5+ págs. / 2.500+ palavras)",
}

_CONTEXTO_GUIDANCE: dict[str, str] = {
    "academico": "Produza um artigo ou monografia acadêmica em formato ABNT",
    "npj": "Atue como um advogado sênior elaborando peças estruturadas, endereçamentos e jurisprudência aplicável",
    "programacao": "Produza documentação técnica ou guia de implementação com linguagem clara e exemplos de código quando relevante",
}

PESQUISA_SYSTEM_PROMPT = """\
Você é o LexNeuro, um assistente jurídico e acadêmico de elite.
Sua missão é inferir a intenção do usuário a partir de instruções \
fragmentadas e produzir um documento final perfeitamente estruturado, \
sem exigir explicações adicionais.

### PARÂMETROS DA SOLICITAÇÃO:
- Tema Central: {tema}
- Contexto: {contexto_label} ({contexto_guidance})
- Extensão Desejada: {extensao_label} (Adeque o nível de detalhe para \
atingir essa proporção aproximada de texto).
- Páginas Solicitadas: {paginas} (Alvo aproximado de páginas no \
documento final. Priorize este número sobre a extensão se houver conflito).
- Modo de Pensamento Ativo: {modo_pensamento} (Se True, explore teses \
minoritárias e debates profundos).
- Diretrizes Extras: {instrucoes_extras}

### REGRAS DE EXECUÇÃO:
1. COMPREENSÃO DE FRAGMENTOS: Se pedido "3 peças", não explique o que \
são. Escreva imediatamente o esqueleto estrutural das 3 peças com base \
no tema.
2. MARKDOWN DISCORD: Use `#` para grandes divisões e `**` para destacar \
artigos de lei (ex: **Art. 319 do CPC**). Use `>` para simular recuos de \
citação direta longa (ABNT).
3. RIGOR (LEX): Nunca invente jurisprudência. Indique competência \
correta e fundamentação real. Se houver divergência, exponha ambas as \
correntes.
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
"""

REFINEMENT_PROMPT = """\
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
"""


def build_pesquisa_messages(
    *,
    tema: str,
    contexto: str = "academico",
    extensao: str = "padrao",
    paginas: int = 3,
    modo_pensamento: bool = False,
    instrucoes_extras: str | None = None,
) -> list[dict[str, Any]]:
    contexto_label = CONTEXTO_LABELS.get(contexto, contexto)
    contexto_guidance = _CONTEXTO_GUIDANCE.get(contexto, "")
    extensao_label = EXTENSAO_LABELS.get(extensao, extensao)
    instrucoes = instrucoes_extras or "Nenhuma"

    system_prompt = PESQUISA_SYSTEM_PROMPT.format(
        tema=tema,
        contexto_label=contexto_label,
        contexto_guidance=contexto_guidance,
        extensao_label=extensao_label,
        paginas=paginas,
        modo_pensamento=modo_pensamento,
        instrucoes_extras=instrucoes,
    )

    abnt_reference = load_abnt_reference()
    system_prompt += (
        f"\n\n## DIRETRIZES OBRIGATÓRIAS DE FORMATAÇÃO ABNT\n\n{abnt_reference}"
    )

    return [
        dict(role="system", content=system_prompt),
        dict(role="user", content=tema),
    ]


def build_refinement_message() -> str:
    return REFINEMENT_PROMPT
