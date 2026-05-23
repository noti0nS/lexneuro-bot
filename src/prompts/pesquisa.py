import re
from typing import Any

from .abnt import load_abnt_reference

EXTENSAO_LABELS: dict[str, str] = {
    "curto": "Direto ao Ponto (~1 pág. / 500 palavras)",
    "padrao": "Padrão (~3 págs. / 1.500 palavras)",
    "completo": "Dossiê Completo (5+ págs. / 2.500+ palavras)",
}

_JURIDICO_KEYWORDS: set[str] = {
    "ação judicial",
    "acórdão",
    "advocacia",
    "alvará",
    "apelação",
    "artigo",
    "cível",
    "civil",
    "clt",
    "código civil",
    "código de processo",
    "código penal",
    "condenação",
    "constituição",
    "constitucional",
    "cpc",
    "cpp",
    "crime",
    "criminal",
    "danos morais",
    "decisão judicial",
    "defensoria",
    "direito",
    "doutrina",
    "embargos",
    "estatuto",
    "fgts",
    "habeas corpus",
    "indenização",
    "inss",
    "juiz",
    "jurídico",
    "jurisprudência",
    "justiça",
    "lei",
    "legislação",
    "liminar",
    "mandado",
    "ministério público",
    "penal",
    "petição",
    "previdência",
    "previdenciário",
    "processo judicial",
    "procuradoria",
    "recorrente",
    "recurso",
    "réu",
    "sentença",
    "stf",
    "stj",
    "sucessão",
    "trabalhista",
    "tribunal",
    "tributário",
    "tutela",
}

_TECNOLOGIA_KEYWORDS: set[str] = {
    "algoritmo",
    "api",
    "app",
    "aws",
    "azure",
    "backend",
    "banco de dados",
    "big data",
    "blockchain",
    "ciência de dados",
    "cloud",
    "código fonte",
    "compilador",
    "computação",
    "criptografia",
    "database",
    "desenvolvimento web",
    "devops",
    "docker",
    "engenharia de software",
    "framework",
    "frontend",
    "hardware",
    "inteligência artificial",
    "java",
    "javascript",
    "kubernetes",
    "linux",
    "machine learning",
    "machine-learning",
    "programação",
    "python",
    "rede neural",
    "rust",
    "segurança da informação",
    "software",
    "sistema operacional",
    "sql",
    "typescript",
    "web",
}

_DOMAIN_INSTRUCTIONS: dict[str, str] = {
    "juridico": """\
- **Domínio Jurídico**: Produza um artigo acadêmico com doutrina, \
jurisprudência e fundamentação legal precisa. Nunca invente jurisprudência \
ou fontes inexistentes. Use **Art. X da Lei Y** para destacar dispositivos \
legais. Se houver divergência doutrinária ou jurisprudencial, exponha ambas \
as correntes. Busque fontes oficiais: tribunais, legislação, artigos \
doutrinários.""",
    "tecnologia": """\
- **Domínio Tecnológico**: Produza documentação técnica ou artigo acadêmico \
com explicações conceituais, exemplos de código quando relevante, e \
referências a frameworks, linguagens e boas práticas. Use ```linguagem \
para blocos de código. Priorize fontes como documentação oficial, artigos \
técnicos e papers acadêmicos.""",
    "geral": """\
- **Domínio Geral/Acadêmico**: Produza um artigo ou texto acadêmico-científico \
sobre o tema. Estruture com introdução, desenvolvimento e conclusão. \
Fundamente-se em fontes acadêmicas, dados e referências bibliográficas do \
campo de conhecimento pertinente. Adapte a terminologia ao domínio do tema. \
Busque fontes acadêmicas confiáveis: artigos científicos, livros, \
periódicos e publicações especializadas.""",
}

PESQUISA_SYSTEM_PROMPT = """\
Você é o LexNeuro, um assistente de pesquisa e documentação acadêmica.
Sua missão é inferir a intenção do usuário a partir de instruções \
fragmentadas e produzir um documento final perfeitamente estruturado, \
sem exigir explicações adicionais.

### PARÂMETROS DA SOLICITAÇÃO:
- Tema Central: {tema}
- Domínio Classificado: **{dominio}**
{domain_instructions}
- Extensão Desejada: {extensao_label} (Adeque o nível de detalhe para \
atingir essa proporção aproximada de texto).
- Páginas Solicitadas: {paginas} — ALVO EXATO. O documento final DEVE \
ter {paginas} página(s) de conteúdo substancial — nem menos, nem mais. \
Se perceber que o texto está curto, aprofunde-se em mais fontes, \
subtópicos ou análises complementares. Se perceber que está longo demais, \
corte os trechos menos essenciais e vá direto ao ponto. Este é o parâmetro \
mais importante — a extensão é secundária, a contagem exata de páginas é \
primária.

### REGRAS DE EXECUÇÃO:
1. COMPREENSÃO DE FRAGMENTOS: Infira a intenção e escreva imediatamente \
o documento estruturado com base no tema.
2. MARKDOWN DISCORD: Use `#` para grandes divisões e `**` para destacar \
termos ou conceitos importantes.
3. RIGOR: Fundamente cada afirmação em fontes reais e verificáveis. \
Se houver divergência na literatura, exponha todas as perspectivas.
4. TOM: Direto, culto, resolutivo. Comece IMEDIATAMENTE com o conteúdo \
do documento — NUNCA diga "Aqui está", "Segue o documento", nem qualquer \
introdução ou comentário meta-textual. Seu output DEVE começar com o \
título ou primeiro parágrafo do documento.
5. CONTAGEM DE PÁGINAS ({paginas}): Esta é a regra mais importante. \
Planeje a estrutura ANTES de redigir: seção por seção, quantos parágrafos \
cada uma terá. Após cada seção, avalie se o volume acumulado está no \
caminho para {paginas} página(s) exatas. Se estiver ficando curto, \
EXPANDA: adicione fontes complementares, contra-argumentos, notas \
explicativas. Se estiver ficando longo, ENXUGUE: corte repetições, \
resuma parágrafos prolixos, remova tangentes. Entregar {paginas} \
página(s) — nem menos, nem mais — é obrigatório. Um documento com \
contagem errada de páginas é uma falha grave.

### FERRAMENTAS DE PESQUISA:
Você tem acesso a `web_search` (busca DuckDuckGo por artigos e fontes) \
e `fetch_page` (conteúdo integral de URLs). Use múltiplas buscas com \
diferentes ângulos. Reúna fontes antes de redigir. Priorize fontes \
confiáveis e acadêmicas.

### FORMATAÇÃO:
- Inclua "REFERÊNCIAS" ao final com citações no formato ABNT NBR 6023.
- Produza APENAS o conteúdo do documento. Qualquer linha que não pertença \
ao documento (introduções como "Aqui está", saudações, explicações sobre \
o que foi gerado) está PROIBIDA.
"""

REFINEMENT_PROMPT = """\
Antes de iniciar a pesquisa, reflita sobre o tema. Formule de 3 a 5 \
perguntas esclarecedoras que um especialista no domínio **{dominio_label}** \
faria e responda cada uma com seu melhor conhecimento sobre o assunto. \
Seja conciso. Não faça buscas — apenas raciocine.

Formato:
### ANÁLISE PRELIMINAR
**Pergunta 1:** [pergunta]
**Resposta:** [resposta]

**Pergunta 2:** [pergunta]
**Resposta:** [resposta]

...

Ao final, prossiga com a pesquisa web e a redação do documento.
"""

_DOMINIO_LABELS: dict[str, str] = {
    "juridico": "jurídico",
    "tecnologia": "tecnologia/programação",
    "geral": "acadêmico-científico",
}


def detect_domain(tema: str) -> str:
    """Detect the domain of a research topic via keyword matching."""
    tema_lower = tema.lower()

    for kw in _JURIDICO_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", tema_lower):
            return "juridico"

    for kw in _TECNOLOGIA_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", tema_lower):
            return "tecnologia"

    return "geral"


DOCUMENT_TOOL_SECTION = """\
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
    extensao_label = EXTENSAO_LABELS.get(extensao, extensao)
    dominio = detect_domain(tema)
    domain_instructions = _DOMAIN_INSTRUCTIONS[dominio]

    system_prompt = PESQUISA_SYSTEM_PROMPT.format(
        tema=tema,
        dominio=dominio,
        domain_instructions=domain_instructions,
        extensao_label=extensao_label,
        paginas=paginas,
    )

    if dominio == "juridico":
        abnt_reference = load_abnt_reference()
        system_prompt += (
            f"\n\n## DIRETRIZES OBRIGATÓRIAS DE FORMATAÇÃO ABNT\n\n{abnt_reference}"
        )

    if has_attachment:
        system_prompt += "\n\n" + DOCUMENT_TOOL_SECTION

    return [
        dict(role="system", content=system_prompt),
        dict(role="user", content=tema),
    ]


def build_refinement_message(dominio: str = "geral") -> str:
    dominio_label = _DOMINIO_LABELS.get(dominio, "acadêmico-científico")
    return REFINEMENT_PROMPT.format(dominio_label=dominio_label)
