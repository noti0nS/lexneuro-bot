# PRD: Status Dinâmico — Dynamic Discord Status Generator

## Overview

### Purpose
Automatically generate and rotate the bot's Discord presence status once per day using a lightweight LLM call, falling back to a locally cached message history and ultimately to the static config value.

### Target Users
Server members who see the bot's status in the member list; no direct user interaction required.

---

## User Flow

```
1. Bot initializes (on_ready)
   └─ Scheduler starts a background loop
2. Loop tick (every 1 hour or on startup)
   ├─ Check SQLite DB for the most recent status message
   ├─ If message exists and is fresh (< 24h old):
   │   └─ Apply that exact message as presence
   │      (Option A: deterministic latest, not random)
   └─ If stale or missing:
      ├─ Call configured LLM with hardcoded prompt
      ├─ On success:
      │   ├─ Store message in SQLite (FIFO rotate if > 100 rows)
      │   └─ Apply as presence
      └─ On any failure:
         ├─ Try to pick a random existing message from DB
         ├─ If DB is empty:
         │   └─ Fall back to config.status_message
         └─ Apply whichever succeeded as presence
3. Repeat from step 2 every hour
```

---

## Configuration

```yaml
# config-example.yaml additions
status:
  enabled: true
  model: "openai/gpt-4o-mini"   # Dedicated model for status generation (can be free)
  interval_hours: 24             # Minimum age before generating a new message
  max_history: 100               # Max rows in SQLite before FIFO rotation
```

The existing top-level key `status_message` is preserved and acts as the **ultimate fallback** when the LLM fails and the DB is empty.

---

## Core Feature Specifications

### SQLite Storage (`src/helpers/status_db.py`)

- **Path**: `data/status.db` (gitignored)
- **Schema**:
  ```sql
  CREATE TABLE IF NOT EXISTS status_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      content TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```
- **Operations**:
  - `init_db()` — creates table and `data/` directory if missing.
  - `add_message(content: str) -> None` — inserts a new row; if `COUNT(*) > max_history`, deletes the oldest row (`MIN(id)`) before inserting.
  - `get_latest_message() -> str | None` — returns the most recently inserted `content`.
  - `get_random_message() -> str | None` — returns a random `content` from history.
  - `get_message_count() -> int` — total rows.

### LLM Prompt Design (`src/helpers/status_generator.py`)

Hardcoded constant (Portuguese, matching bot theme):

```text
Generate 1 short Discord bot status for LexNeuro.
Cute, smart, study/productivity theme.
Max 80 characters.
Return only the status text.
```

- **Non-streaming** call following the `pesquisa.py` pattern.
- **Max tokens**: `128` ( Discord limit is 128 chars; truncation to `[:128]` applied as safety).
- Uses `build_openai_chat_completion_kwargs(..., stream=False)`.
- Wrapped in `await_task_with_heartbeats(...)`.

### Scheduler (`src/helpers/status_scheduler.py`)

- Uses `discord.ext.tasks.loop(hours=1)`.
- `on_ready` calls `update_status()` immediately before starting the loop.
- `update_status()` flow:
  1. Fetch hot-reloaded config via `await asyncio.to_thread(get_config)`.
  2. If `status.enabled` is `false`, apply `config.status_message` and return.
  3. Load `latest = get_latest_message()`.
  4. If `latest` exists and `created_at` is within `interval_hours`, call `bot.change_presence` with `latest` and return.
  5. Otherwise attempt LLM generation via `generate_status_message(...)`.
  6. On success: `add_message(result)` then `change_presence`.
  7. On failure: `random = get_random_message()`. If `random` exists, `change_presence` with it. Else `change_presence` with `config.status_message`.

### Bot Integration (`src/bot.py`)

- Import `start_status_scheduler` from `src/helpers/status_scheduler`.
- Inside `on_ready`, after `tree.sync()`, call `start_status_scheduler(discord_bot)`.
- Remove the one-time `discord.CustomActivity` construction at bot creation (or keep it as initial placeholder until `on_ready` fires).

---

## Files to Create/Modify

| File | Action |
|---|---|
| `prd/status-dinamico.md` | **Create** — this PRD |
| `src/helpers/status_db.py` | **Create** — SQLite init, insert, fetch latest, fetch random, rotate |
| `src/helpers/status_generator.py` | **Create** — hardcoded prompt + non-streaming LLM call |
| `src/helpers/status_scheduler.py` | **Create** — `discord.ext.tasks` loop + update logic |
| `src/bot.py` | **Edit** — start scheduler in `on_ready`; remove or defer static activity init |
| `config-example.yaml` | **Edit** — add `status:` block |
| `.gitignore` | **Edit** — add `data/` directory |
| `tests/test_status.py` | **Create** — unit tests for DB, generator, scheduler logic |

---

## Edge Cases & Error Handling

| Case | Behavior |
|---|---|
| `status.enabled` is `false` or missing | Apply static `config.status_message` and stop scheduler loop. |
| `status.model` is invalid / provider missing | Log error, fallback to DB random → config `status_message`. |
| LLM returns empty content | Treat as failure → DB random → config fallback. |
| LLM content > 128 chars | Truncate to `[:128]` before storing and applying. |
| LLM provider error (APIError, timeout) | Log exception, fallback chain as above. |
| SQLite file is corrupted / unreadable | Log exception, fallback to config `status_message`. |
| DB has exactly 100 rows and new message arrives | Delete oldest row (`MIN(id)`) before insert (FIFO rotation). |
| Bot restarts within 24h | `get_latest_message()` returns fresh row → same status applied immediately, no LLM call. |
| `interval_hours` changed to a smaller value while bot is running | Next loop tick respects the new value because config is hot-reloaded. |
| Discord rate-limits `change_presence` | `discord.py` handles backoff internally; status may lag slightly. |

---

## Example Interaction

No direct user interaction. The feature is fully autonomous.

Bot startup log:
```
[INFO] Status scheduler started (interval=1h, model=openai/gpt-4o-mini)
[INFO] Latest DB message is fresh (age=4h). Applying: "📚 Modo foco ativado!"
```

24 hours later:
```
[INFO] Latest DB message is stale (age=25h). Generating new status...
[INFO] LLM status generated: "☕ Café + código = produtividade"
[INFO] Status stored and applied.
```

On LLM failure:
```
[ERROR] Failed to generate status: APIError(code=429)
[INFO] Fallback to random DB message: "🎯 Meta do dia: 1% melhor"
```

---

## Testing

Test file: `tests/test_status.py`

- `test_init_db_creates_table_and_directory` — `init_db()` creates `data/status.db` and schema.
- `test_add_message_inserts_and_increments_count` — basic insert + `get_message_count()`.
- `test_add_message_rotates_fifo_at_max_history` — insert 101 rows, verify oldest deleted, count == 100.
- `test_get_latest_message_returns_most_recent` — insert A then B, verify B returned.
- `test_get_random_message_returns_existing_content` — insert rows, verify returned value is in set.
- `test_get_random_message_empty_db` — empty DB returns `None`.
- `test_generate_status_message_returns_truncated_text` — mock LLM returning 200 chars, verify result is 128.
- `test_generate_status_message_returns_none_on_api_error` — mock APIError, verify `None`.
- `test_update_status_applies_latest_when_fresh` — mock DB latest within interval, verify `change_presence` called with it.
- `test_update_status_generates_when_stale` — mock DB latest older than interval, verify LLM called and result stored.
- `test_update_status_fallback_to_random_on_llm_error` — mock LLM failure + DB has random row, verify random applied.
- `test_update_status_fallback_to_config_when_db_empty` — mock LLM failure + empty DB, verify `config.status_message` applied.
- `test_update_status_respects_enabled_false` — `status.enabled=false`, verify static config applied and no LLM call.

---

## Out of Scope & Future Enhancements

### Out of Scope (v1)
- Manual `/status` slash command to force regeneration.
- Per-guild customizable status messages.
- Status message themes or seasonal variants.
- Image/rich presence activities (only `CustomActivity` text).
- Web dashboard to browse history.

### Future Enhancements
- `/status` admin command to trigger on-demand generation.
- Weighted random selection (favor recent or highly-rated messages).
- A/B testing two status prompts and measuring engagement.
- Export history to CSV.
- Multiple status messages per day with different time-of-day themes.
