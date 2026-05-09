import os
import sqlite3

_DEFAULT_DB_DIR = "data"
_DEFAULT_DB_NAME = "bot.db"


def get_db_path(db_name: str = _DEFAULT_DB_NAME) -> str:
    return os.path.join(_DEFAULT_DB_DIR, db_name)


def get_connection(db_name: str = _DEFAULT_DB_NAME) -> sqlite3.Connection:
    return sqlite3.connect(get_db_path(db_name))


def init_db() -> None:
    os.makedirs(_DEFAULT_DB_DIR, exist_ok=True)
    conn = get_connection()
    try:
        _ensure_status_history_table(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_status_history_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )