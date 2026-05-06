from datetime import date

CRONOGAMA_SYSTEM_PROMPT = """\
Você é um planejador de estudos brasileiro. Sua função é montar um cronograma de estudos personalizado e conciso para um estudante que tem provas chegando.

Regras:
- Distribua as matérias ao longo de TODOS os dias listados no calendário abaixo.
- Cada dia comporta no máximo {hours_per_day}h de estudo.
- Em cada dia, distribua 1-3 matérias, com tempo estimado por matéria.
- A soma dos tempos do dia NÃO deve ultrapassar {hours_per_day}h.
- Inclua revisões periódicas antes da prova.
- Deixe o(s) último(s) dia(s) antes da prova como revisão geral/descanso leve.
- Adapte a carga horária conforme a proximidade da prova.
- Seja encorajador mas realista.
- Seja CONCISO: use formato compacto, sem explicações longas. O estudante precisa de um plano claro e direto.
- Use markdown para formatar: negrito para dias, listas para matérias.

Responda APENAS com o cronograma — sem introduções, sem "claro!", sem comentários.
"""

_MONTHS_PT = (
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
)

_WEEKDAY_NAMES = {
    0: "Seg",
    1: "Ter",
    2: "Qua",
    3: "Qui",
    4: "Sex",
    5: "Sáb",
    6: "Dom",
}


def format_date_pt(d: date) -> str:
    return (
        f"{_WEEKDAY_NAMES[d.weekday()]} {d.day:02d}/{_MONTHS_PT[d.month - 1]}/{d.year}"
    )


def build_cronograma_messages(
    *,
    test_date: date,
    subjects: str,
    hours_per_day: int,
    instructions: str | None,
    calendar_dates: list[date],
) -> list[dict[str, str]]:
    system_prompt = CRONOGAMA_SYSTEM_PROMPT.format(hours_per_day=hours_per_day)

    lines: list[str] = []
    lines.append(f"Data da prova: {format_date_pt(test_date)}")
    lines.append(f"Matérias: {subjects}")
    lines.append(f"Horas disponíveis por dia: {hours_per_day}h")
    lines.append(f"Instruções adicionais: {instructions or 'Nenhuma'}")
    lines.append("")
    lines.append("Calendário de estudo:")
    for d in calendar_dates:
        lines.append(f"- {format_date_pt(d)}")

    user_prompt = "\n".join(lines)

    return [
        dict(role="system", content=system_prompt),
        dict(role="user", content=user_prompt),
    ]
