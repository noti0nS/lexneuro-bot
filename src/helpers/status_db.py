from ..db import get_connection


def add_message(content: str, max_history: int = 100) -> None:
    if not content.strip():
        return

    conn = get_connection()
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
    conn = get_connection()
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
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT content FROM status_history ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_message_count() -> int:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) FROM status_history").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()