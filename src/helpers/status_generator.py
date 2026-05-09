import asyncio
import random
import logging

from openai import APIError, AsyncOpenAI

from ..config import OpenAIRequestConfig, build_openai_chat_completion_kwargs
from ..helpers.async_utils import await_task_with_heartbeats
from ..helpers.content import get_completion_text

STATUS_PROMPTS = [
    (
        "Gere 1 status curto e criativo para o bot Discord LexNeuro. "
        "Seja inventivo: use metáforas jurídicas, referências a processos, "
        "tribunais, artigos de lei, ou situações engraçadas de quem estuda Direito. "
        "Pode ser poético, irônico, motivacional ou absurdo. "
        "Max 80 caracteres. Responda APENAS o status em pt-br, sem aspas nem explicações."
    ),
    (
        "Crie 1 frase de status para o bot LexNeuro que seria engraçada num servidor de estudantes de Direito. "
        "Pense em: dormindo com o CPC debaixo do travesseiro, código penal como leitura de ninar, "
        "ou julgamentos imaginários no churrasco. Max 80 caracteres. "
        "Responda APENAS o status em pt-br, sem aspas."
    ),
    (
        "Gere 1 status curto pro LexNeuro que misture estudo de Direito com vida real de forma inteligente. "
        "Ex: 'objeto ilícito? meu sono' ou 'apelou mas esqueceu o prazo'. "
        "Seja criativo e surpreendente. Max 80 caracteres. "
        "Responda APENAS o status em pt-br."
    ),
    (
        "Imagine um status de Discord que um estudante de Direito colocaria e sorriria. "
        "Pode ter jargão jurídico, gíria de tribunal, referência a constituição ou STF. "
        "Seja leve e divertido. Max 80 caracteres. "
        "Responda APENAS o status em pt-br, sem explicação."
    ),
    (
        "Crie 1 status para o bot LexNeuro que soe como um advogado preocupado teria no WhatsApp. "
        "Pode ser sobre prazos, petições, audiências, café, ou o eterno 'uma segunda opinião'. "
        "Max 80 caracteres. Responda APENAS o status em pt-br."
    ),
    (
        "Gere 1 micro-frase de status pro LexNeuro: algo que um jurista diria no elevator pitch. "
        "Pode ser um trocadilho legal, um aforismo fake, ou uma verdade universal de quem faz concurso. "
        "Max 80 caracteres. Responda APENAS o status em pt-br, sem pontuação extra."
    ),
]

MAX_STATUS_CHARS = 128


async def generate_status_message(
    openai_client: AsyncOpenAI,
    openai_config: OpenAIRequestConfig,
) -> str | None:
    prompt = random.choice(STATUS_PROMPTS)
    messages = [
        {"role": "user", "content": prompt},
    ]

    try:
        completion_task = asyncio.create_task(
            openai_client.chat.completions.create(
                **build_openai_chat_completion_kwargs(
                    openai_config,
                    messages,
                    stream=False,
                    max_tokens=MAX_STATUS_CHARS,
                )
            )
        )
        completion = await await_task_with_heartbeats(
            completion_task,
            "Status generation LLM request still running",
        )

        raw = get_completion_text(completion)
        if not raw or not raw.strip():
            logging.warning("Status generation returned empty content")
            return None

        result = raw.strip().strip('"\'').strip()[:MAX_STATUS_CHARS]
        logging.info("Status generated: %s", result)
        return result

    except APIError:
        logging.exception("Status generation failed with API error")
        return None
    except Exception:
        logging.exception("Status generation failed")
        return None