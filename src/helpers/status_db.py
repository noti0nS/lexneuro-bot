import logging
import os
import sqlite3


def _db_path() -> str:
    return os.path.join("data", "status.db")


_db_initialized = False


def init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return

    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    _db_initialized = True
    logging.info("Status DB initialized at %s", _db_path())


def add_message(content: str, max_history: int = 100) -> None:
    if not content.strip():
        return

    conn = sqlite3.connect(_db_path())
    try:
        conn.execute("INSERT INTO status_history (content) VALUES (?)", (content,))
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM status_history").fetchone()
        if count and count[0] > max_history:
            oldest_id = conn.execute("SELECT MIN(id) FROM status_history").fetchone()
            if oldest_id and oldest_id[0] is not None:
                conn.execute("DELETE FROM status_history WHERE id = ?", (oldest_id[0],))
                conn.commit()
    finally:
        conn.close()


def get_latest_message() -> tuple[str, str] | None:
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute(
            "SELECT content, created_at FROM status_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return row[0], row[1]
        return None
    finally:
        conn.close()


def get_random_message() -> str | None:
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute(
            "SELECT content FROM status_history ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_message_count() -> int:
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute("SELECT COUNT(*) FROM status_history").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()
