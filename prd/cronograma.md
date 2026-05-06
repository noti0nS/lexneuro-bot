# PRD: `/cronograma` — Study Schedule Generator

## Summary

`/cronograma` generates a personalized study schedule (cronograma de estudos). The user provides the test/exam start date, subject list, hours per day, and which weekdays they can study. The bot computes the calendar window (today → a few days before test), maps weekdays to concrete dates, and calls the LLM to produce a day-by-day study plan covering all subjects.

## User flow

```
1. User types /cronograma test_date=YYYY-MM-DD subjects="..."
   hours_per_day=4
2. Bot replies ephemeral with a multi-select component listing the 7 weekdays
3. User checks off which weekdays they can study (e.g. segunda, terça, sábado)
   and clicks Submit
4. Bot defers the interaction, computes the calendar (concrete dates in the
   study window filtered to the selected weekdays), calls the LLM
5. LLM returns the cronograma; bot sends it as the deferred response
```

### Slash command parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `test_date` | STRING | Yes | — | First day of tests/exams. Format `YYYY-MM-DD`. Must be ≥3 days in the future. |
| `subjects` | STRING | Yes | — | Comma-separated or free-text list of subjects. e.g. `Direito Civil, Processo Penal, Constitucional`. |
| `hours_per_day` | NUMBER | No | config `cronograma.default_hours_per_day` (default 4) | How many hours per day the user has available for studying. Sent to the LLM as a constraint. |
| `instructions` | STRING | No | — | Optional extra instructions. e.g. "foco mais em Civil, já domino Penal", "prefiro estudar 2 matérias por dia". |

Why `test_date` is STRING: Discord has no native date argument type. Use `app_commands.Transform` + a custom transformer to validate `YYYY-MM-DD` and convert to `datetime.date`.

### Calendar generation (happens after weekday selection)

Given `test_date` and `today`:

1. Compute the study window: `today + 1` (tomorrow) to `test_date - N` where N = `cronograma.days_before_test` (config, default **3**).
2. Generate every date in that range.
3. Filter to only dates whose weekday matches one of the **selected weekdays**.
4. Format each date as e.g. `Seg 18/Mai/2026` (short month name in PT-BR).
5. Sort chronologically.
6. If the filtered list is empty: the study window has no matching weekdays → reply ephemeral "Nenhum dia de estudo disponível com essa combinação de dias da semana."

The filtered date list is what gets passed to the LLM prompt as the concrete calendar.

### Weekday selector (multi-select component)

After the slash command invocation, the bot calls `interaction.response.send_message(ephemeral=True)` with:

- A `discord.ui.View` containing a `discord.ui.StringSelect` with `min_values=1`, `max_values=7`.
- 7 fixed options:

| Label | Value |
|---|---|
| `Segunda-feira` | `segunda` |
| `Terça-feira` | `terca` |
| `Quarta-feira` | `quarta` |
| `Quinta-feira` | `quinta` |
| `Sexta-feira` | `sexta` |
| `Sábado` | `sabado` |
| `Domingo` | `domingo` |

- View also includes a `discord.ui.Button` label `Confirmar` with `style=Primary`.

On button click (submit):
- The view is disabled (`disable_all_items()`).
- Selected weekday strings are extracted from the select.
- Interaction is deferred: `await interaction.response.defer()`.
- Calendar computation runs → filtered date list.
- Prompt is built → LLM call begins.

On timeout:
- `on_timeout()` disables all items, edits message to "Tempo esgotado. Execute /cronograma novamente."

### LLM prompt design

Prompt built in `src/prompts/cronograma.py` following the `abnt.py` / `pesquisa.py` pattern.

#### System prompt

```text
Você é um planejador de estudos brasileiro. Sua função é montar um cronograma
de estudos personalizado para um estudante que tem provas chegando.

Regras:
- Distribua as matérias ao longo de TODOS os dias listados no calendário abaixo.
- Cada dia comporta no máximo {hours_per_day}h de estudo.
- Em cada dia, distribua 1-3 matérias, com tempo estimado por matéria.
- A soma dos tempos do dia NÃO deve ultrapassar {hours_per_day}h.
- Inclua revisões periódicas antes da prova.
- Deixe o(s) último(s) dia(s) antes da prova como revisão geral/descanso leve.
- Adapte a carga horária conforme a proximidade da prova.
- Use markdown do Discord para formatar (negrito, listas, blocos de código).
- Seja encorajador mas realista.

Responda APENAS com o cronograma — sem introduções, sem "claro!", sem comentários.
```

#### User message (constructed dynamically)

```text
Data da prova: 15/Jun/2026
Matérias: Direito Civil, Processo Penal, Constitucional
Horas disponíveis por dia: 4h
Instruções adicionais: foco mais em Civil

Calendário de estudo:
- Seg 18/Mai/2026
- Seg 25/Mai/2026
- Seg 01/Jun/2026
- Seg 08/Jun/2026
- Ter 19/Mai/2026
- Ter 26/Mai/2026
- Ter 02/Jun/2026
- Ter 09/Jun/2026
- Sáb 23/Mai/2026
- Sáb 30/Mai/2026
- Sáb 06/Jun/2026
```

The date list is pre-filtered to the user's selected weekdays. Only matching dates appear. The LLM should allocate study to every date in the list.

### LLM call pattern

Follow the `pesquisa.py` pattern (non-streaming completions with `await_task_with_heartbeats`):

1. Build messages via `build_cronograma_messages(test_date, subjects, hours_per_day, instructions, selected_weekdays, calendar_dates)`.
2. Call `openai_client.chat.completions.create(**build_openai_chat_completion_kwargs(openai_config, messages, stream=False))`.
3. Wrap in `await_task_with_heartbeats(...)`.
4. On success: `interaction.edit_original_response(content=output)`.
5. On error: `interaction.followup.send(...)`.

Why non-streaming: the output is a single document (a schedule). Streaming adds complexity for long cronogramas. Start simple, add streaming later if needed.

### Config keys (`config-example.yaml`)

```yaml
cronograma:
  days_before_test: 3            # days before test the schedule ends
  default_hours_per_day: 4       # fallback hours when user omits hours_per_day
```

No `max_visible_days` key — the select menu has exactly 7 options (weekdays), always fits the Discord limit.

### Files to create/modify

| File | Action |
|---|---|
| `src/commands/cronograma.py` | **Create** — slash command registration, weekday select + button, calendar computation, LLM orchestration |
| `src/prompts/cronograma.py` | **Create** — `build_cronograma_messages()`, system/user prompt templates |
| `src/prompts/__init__.py` | **Edit** — add export for `build_cronograma_messages` |
| `src/commands/__init__.py` | (no change) |
| `src/bot.py` | **Edit** — import and call `register_cronograma_command(...)` |
| `config-example.yaml` | **Edit** — add `cronograma` section |
| `pyproject.toml` | (no change — `datetime` is stdlib) |

### Edge cases & error handling

| Case | Behavior |
|---|---|
| `test_date` is in the past or today | Ephemeral: "A data da prova deve ser no futuro." |
| `test_date` is <3 days away | Ephemeral: "A prova está muito próxima. Não há janela de estudo suficiente." |
| `test_date` format is invalid | Ephemeral: "Use o formato YYYY-MM-DD (ex: 2026-06-15)." |
| `subjects` is empty | Ephemeral: "Informe pelo menos uma matéria." |
| `hours_per_day` <= 0 | Ephemeral: "As horas por dia devem ser positivas." |
| `hours_per_day` > 16 | Ephemeral: "Ninguém estuda {hours_per_day}h por dia. Seja realista." (cap or warn) |
| Weekday select: no matching dates in window | Ephemeral: "Nenhum dia de estudo disponível com essa combinação de dias da semana." |
| View times out before user clicks Confirmar | Disable all items, edit message: "Tempo esgotado. Execute /cronograma novamente." |
| User doesn't have permission | `user_has_permission(...)` check. Ephemeral rejection. |
| LLM provider error | `followup.send(...)` with provider detail (same pattern as ABNT/research). |
| LLM returns empty output | `followup.send(...)` "Não foi possível gerar o cronograma." |

### Example interaction

```
User:
  /cronograma test_date=2026-06-15
              subjects=Direito Civil, Processo Penal, Constitucional
              hours_per_day=4

Bot (ephemeral, with select menu + button):
  Selecione os dias da semana em que você pode estudar:
  ┌─────────────────────────────────────┐
  │ ✅ Segunda-feira    ☐ Quinta-feira │
  │ ✅ Terça-feira      ☐ Sexta-feira  │
  │ ☐ Quarta-feira     ✅ Sábado       │
  │                     ☐ Domingo      │
  │         [Confirmar seleção]         │
  └─────────────────────────────────────┘

User checks Seg, Ter, Sáb. Clicks Confirmar.

Bot defers, computes calendar (all Seg, Ter, Sáb from 19/Mai to 12/Jun),
calls LLM, sends result:

  📅 Cronograma de Estudos — Prova: 15/Jun/2026 (4h/dia)

  **Seg 19/Mai**
  - Direito Civil (2h30) — Responsabilidade Civil
  - Processo Penal (1h30) — Princípios e sistemas

  **Ter 20/Mai**
  - Constitucional (2h) — Controle de constitucionalidade
  - Direito Civil (2h) — Obrigações

  **Sáb 24/Mai**
  - Processo Penal (2h) — Inquérito policial
  - Constitucional (2h) — Remédios constitucionais

  ... (continues for all matching dates)

  **Qui 12/Jun** — Revisão geral leve + descanso
  **Sex 13/Jun** — Descanso total antes da prova

  💡 Dica: Revise os resumos nos dias 12-14/Jun.
```

### Testing

Test file: `tests/test_cronograma.py`

Test cases:
- `test_parse_test_date_valid` — `"2026-06-15"` → `date(2026, 6, 15)`
- `test_parse_test_date_invalid` — garbage strings, wrong format → ValueError
- `test_calendar_window_computation` — correct date range, filtered to selected weekdays
- `test_calendar_window_empty_when_no_weekdays_match` — e.g. window has no Mondays
- `test_calendar_window_too_short` — test_date < 3 days away → empty window
- `test_build_messages` — generated messages have correct structure, dates list matches filtered output
- `test_build_messages_includes_hours_per_day` — user message contains the hours constraint
- `test_weekday_select_options_count` — always exactly 7 options
- `test_hours_per_day_validation` — rejects <= 0, warns or caps > 16

### Out of scope / Future enhancements

- **Pomodoro timer integration**: embed time-block suggestions (e.g. 25min focus + 5min break)
- **Progress tracking**: user marks days as "completed", regenerates updated cronograma
- **Multiple test dates**: handle concurrent exam periods (vestibular, OAB)
- **Refinement after generation**: user can reply "add weekends" / "remove Civil" and the LLM regenerates
- **Streaming output**: switch to streaming for better UX on long cronogramas
- **Calendar iCal export**: generate `.ics` file the user can import into Google Calendar
