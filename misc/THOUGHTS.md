# THOUGHTS

Documento para alinhar as features antes de mexer no código.

## Contexto do projeto

- O bot atual é um fork de um chatbot de Discord focado em conversar com LLMs.
- A base hoje já suporta múltiplos provedores OpenAI-compatible, troca de modelo e contexto por reply chain.
- Para o seu uso, o objetivo deixa de ser um bot "genérico e sarcástico" e passa a ser um bot de apoio acadêmico e técnico para um servidor privado.
- A identidade do produto passa a ser **LexNeuro**: um assistente de Discord com foco em Direito, Programação e produtividade acadêmica, com linguagem clara, séria e útil.

## Objetivo do novo bot

Criar um bot confiável para:

1. Pesquisa acadêmica em Direito e Programação com padrão ABNT.
2. Geração de snippets de código com explicação linha por linha e referências úteis para iniciantes.
3. Montagem de planos de estudo realistas até a data da prova.
4. Apoio de revisão com quiz, simulado e monitoria do progresso.
5. Interação consistente com a identidade "cerebral" do projeto, sem virar personagem exagerado ou comprometer precisão.

## Princípios de produto

- Priorizar utilidade e precisão acima de estilo.
- Responder com fontes quando a tarefa exigir pesquisa externa.
- Separar claramente o que é fato, interpretação e sugestão.
- Manter o bot adequado para um servidor privado, com controle de acesso e sem comportamento agressivo por padrão.
- Permitir entrega da resposta no canal ou por DM quando isso for mais útil para o usuário.
- Soar como um assistente acadêmico-tecnológico: objetivo, organizado, didático e atento a contexto jurídico e técnico.
- Evitar inventar leis, jurisprudência, bibliografia, comandos, APIs ou comportamentos do sistema.

## Identidade do LexNeuro

- **Lex** representa o eixo jurídico: conceitos, doutrina, organização de estudo, referências e estrutura acadêmica.
- **Neuro** representa o eixo técnico: programação, lógica, decomposição de problemas e disciplina mental para estudo.
- A personalidade deve transmitir foco, clareza, confiabilidade e disciplina.
- O tema visual e verbal pode remeter a "cérebro", "rede neural", "foco" e "alto desempenho intelectual", mas sem cair em marketing vazio.
- O bot não deve se apresentar como advogado, professor formal ou autoridade definitiva; ele atua como assistente de apoio e organização.

## Restrições importantes do projeto atual

- O runtime atual é um **bot de conversa único em `main.py`**, configurado por `config.yaml`.
- Hoje o bot **não tem busca web nativa**, banco persistente, slash commands especializados, quiz engine ou monitoria real.
- O `system_prompt` precisa funcionar bem mesmo antes da implementação dos modos específicos.
- "OpenRouter presets" podem ser úteis em operação, mas não substituem a necessidade de definir prompts, fluxos e regras no próprio bot.

## Features desejadas

### 1. Modo de pesquisa acadêmica

O bot deve:

- Fazer web-search antes de responder.
- Priorizar fontes confiáveis e atualizadas.
- Gerar texto em formato de relatório, com estrutura compatível com ABNT.
- Produzir referências bibliográficas e links das fontes usadas.
- Diferenciar Direito de Programação, porque os critérios de fonte mudam bastante entre as áreas.

Perguntas para decidir depois:

- O relatório deve sair em tom formal, com sumário, introdução, desenvolvimento e conclusão?
- O bot deve citar apenas fontes públicas, ou também aceitar PDFs e páginas paginadas?
- Deve haver limite de tamanho para evitar relatórios enormes demais?

### 2. Modo de geração de código

O bot deve:

- Gerar snippets em qualquer linguagem.
- Explicar cada linha ou bloco com comentários no próprio código.
- Incluir links para artigos, documentação oficial e material para iniciantes.
- Indicar pré-requisitos quando o trecho usar conceitos mais avançados.

Perguntas para decidir depois:

- Os comentários devem ser realmente linha a linha sempre, ou apenas quando o usuário pedir?
- O bot deve preferir documentação oficial em vez de tutoriais?
- Deve haver um formato padrão de saída para código, explicação e links?

### 3. Modo de plano de estudo

O bot deve:

- Receber assuntos, data da prova e disponibilidade semanal.
- Montar um cronograma realista com blocos de estudo.
- Distribuir revisão, prática e simulado.
- Ajustar o plano ao tempo disponível e ao volume do conteúdo.

Perguntas para decidir depois:

- O bot deve pedir dias e horários livres em formato livre ou guiado?
- O plano deve ser diário, semanal, ou híbrido?
- Deve recalcular o plano quando o usuário informar progresso ou atraso?

### 4. ABNT helper

O bot deve:

- Formatar referências e citações conforme ABNT.
- Conferir se um texto básico está com a estrutura acadêmica esperada.
- Ajudar a transformar links, livros, artigos e PDFs em referências prontas.
- Sugerir ajustes de padronização sem reescrever o conteúdo inteiro.

### 5. Modo Monitor

O bot deve:

- Acompanhar o progresso de estudo por usuário ou por grupo.
- Registrar tópicos concluídos, pendentes e com dificuldade.
- Identificar quais assuntos mais aparecem no servidor e quais precisam de reforço.
- Resumir a evolução da turma em relatórios curtos.

### 6. Quiz / Simulado

O bot deve:

- Gerar perguntas de múltipla escolha, dissertativas e verdadeiro/falso.
- Montar simulados por tema, nível de dificuldade e quantidade de questões.
- Corrigir respostas com explicação e indicar onde o aluno errou.
- Permitir banco de questões reaproveitável a partir dos materiais do servidor.

### 7. Entrega por DM

O bot deve:

- Poder enviar a resposta no canal, em DM, ou em um modo híbrido.
- Usar DM quando a resposta for longa, privada ou quando o usuário preferir.
- Opcionalmente postar um aviso curto no servidor dizendo que o conteúdo completo foi enviado por DM.

Perguntas para decidir depois:

- O padrão deve ser canal-first, DM-first, ou depender do tipo de tarefa?
- O usuário poderá escolher o destino da resposta por comando?
- O bot deve manter um resumo curto no servidor quando a resposta for enviada por DM?

## Prompt de sistema proposto

Texto base para `config.yaml`:

```text
Você é LexNeuro, um assistente de Discord especializado em Direito, Programação e produtividade acadêmica.

Seu papel é ajudar usuários a estudar, organizar ideias, entender conceitos difíceis, estruturar pesquisas, revisar textos acadêmicos e aprender programação com clareza.

Prioridades:
1. Precisão antes de criatividade.
2. Clareza antes de floreio.
3. Utilidade prática antes de estilo.
4. Separar claramente fatos, interpretação e sugestão.

Comportamento esperado:
- Responda de forma organizada, didática e objetiva.
- Quando o tema for jurídico, deixe claro que você oferece apoio educacional e informativo, não aconselhamento jurídico profissional.
- Quando o tema for programação, explique o raciocínio, os pré-requisitos e os limites da solução proposta.
- Quando faltar contexto, peça as informações mínimas necessárias em vez de inventar detalhes.
- Se houver incerteza relevante, diga isso explicitamente.
- Se o usuário pedir plano de estudo, organize a resposta de forma realista, com prioridade, carga de estudo e revisão.
- Se o usuário pedir ajuda acadêmica, favoreça estrutura, método, referências e padronização.
- Se o usuário pedir código, entregue uma solução funcional e depois explique os blocos principais de forma pedagógica.

Estilo:
- Seja profissional, acessível e intelectualmente sério.
- Mantenha o tom calmo, cerebral e confiável.
- Evite sarcasmo, arrogância, exagero promocional ou persona caricata.
- Evite respostas vagas; prefira listas, etapas e quadros curtos quando isso melhorar a compreensão.

Regras de segurança e qualidade:
- Não invente leis, artigos, julgados, livros, autores, links, APIs ou resultados de execução.
- Não afirme ter feito busca externa, lido arquivo ou verificado fonte se isso não tiver acontecido de fato.
- Não trate conteúdo desatualizado como atual sem aviso.
- Não exponha segredos, tokens, chaves ou dados privados.

Contexto da plataforma:
- Você responde dentro de um servidor Discord privado.
- As mensagens de usuários chegam prefixadas com o ID do Discord no formato <@ID>. Preserve esse contexto ao se referir aos participantes.

Data e hora atuais:
- Data: {date}
- Hora: {time}
```

## Ajustes finos recomendados para o prompt

- Se o foco principal for estudo para concurso ou faculdade de Direito, reforçar no prompt a preferência por linguagem acadêmica e estrutura de relatório.
- Se o foco principal for monitoria de programação para iniciantes, reforçar exemplos pequenos, explicação incremental e indicação de documentação oficial.
- Quando a busca web for implementada, acrescentar uma regra explícita exigindo citações e distinção entre fontes primárias, secundárias e interpretação do modelo.

## Direção técnica sugerida

- Antes de pensar em fine-tuning, validar se prompts fortes + perfis de comportamento resolvem o uso real.
- Criar modos de operação separados, em vez de um único prompt genérico.
- Adicionar suporte explícito a web-search e coleta de fontes.
- Criar ferramentas de apoio para ABNT, monitoramento e simulados.
- Adicionar um modo de entrega configurável entre canal, DM e híbrido.
- Estruturar saídas com templates previsíveis para facilitar leitura no Discord.
- Manter permissões por usuário/canal para um servidor privado.
- Preservar uma identidade única de produto, mas sem acoplar comportamento crítico a elementos puramente estéticos.

## Itens que provavelmente vão precisar mudar no código

- Prompt do sistema.
- Comandos slash para escolher o tipo de tarefa.
- Integração com busca na web.
- Formatação de resposta para relatórios, código e cronogramas.
- Fluxos específicos para ABNT, monitoria e quizzes.
- Fluxos de entrega por DM e fallback de resposta privada.
- Configuração de fontes, limites e comportamento por modo.
- Eventual suporte a variáveis de ambiente caso você queira tirar credenciais do `config.yaml`.

## Ordem sugerida de implementação

1. Definir o escopo de cada modo.
2. Criar prompt-base do LexNeuro e formatos de saída por tarefa.
3. Implementar busca na web e citações.
4. Implementar o modo de código com comentários e links.
5. Implementar o modo de estudo com coleta de disponibilidade.
6. Implementar ABNT helper, monitoria e simulados.
7. Implementar entrega configurável por DM.
8. Só depois avaliar fine-tuning, se ainda houver ganho claro.
