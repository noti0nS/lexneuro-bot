import asyncio
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest

from src.helpers import status_generator
from src.helpers.status_db import (
    add_message,
    get_latest_message,
    get_message_count,
    get_random_message,
)


@pytest.fixture
def temp_status_db(monkeypatch: pytest.MonkeyPatch) -> str:
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "bot.db")

    import src.db as db_module

    def _temp_db_path(db_name: str = "bot.db") -> str:
        return db_path

    monkeypatch.setattr(db_module, "get_db_path", _temp_db_path)

    from src.db import init_db as db_init_db

    db_init_db()
    return db_path


class TestStatusDB:
    def test_init_db_creates_table(self, temp_status_db: str) -> None:
        conn = sqlite3.connect(temp_status_db)
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='status_history'"
            ).fetchall()
            assert len(tables) == 1
        finally:
            conn.close()

    def test_add_message_increases_count(self, temp_status_db: str) -> None:
        assert get_message_count() == 0
        add_message("Test status 1")
        assert get_message_count() == 1
        add_message("Test status 2")
        assert get_message_count() == 2

    def test_add_message_ignores_empty(self, temp_status_db: str) -> None:
        add_message("   ")
        assert get_message_count() == 0

    def test_get_latest_message_returns_most_recent(self, temp_status_db: str) -> None:
        add_message("First")
        add_message("Second")
        result = get_latest_message()
        assert result is not None
        assert result[0] == "Second"
        assert result[1] is not None

    def test_get_latest_message_empty_db(self, temp_status_db: str) -> None:
        assert get_latest_message() is None

    def test_get_random_message_returns_existing(self, temp_status_db: str) -> None:
        add_message("A")
        add_message("B")
        add_message("C")
        result = get_random_message()
        assert result in ("A", "B", "C")

    def test_get_random_message_empty_db(self, temp_status_db: str) -> None:
        assert get_random_message() is None

    def test_fifo_rotation_at_max_history(self, temp_status_db: str) -> None:
        max_history = 5
        for i in range(max_history + 2):
            add_message(f"Status {i}", max_history=max_history)

        assert get_message_count() == max_history
        latest = get_latest_message()
        assert latest is not None
        assert latest[0] == f"Status {max_history + 1}"

        conn = sqlite3.connect(temp_status_db)
        try:
            rows = conn.execute(
                "SELECT id, content FROM status_history ORDER BY id"
            ).fetchall()
            first_id = rows[0][0]
            assert first_id > 1
        finally:
            conn.close()

    def test_init_db_is_idempotent(self, temp_status_db: str) -> None:
        from src.db import init_db as db_init_db

        db_init_db()
        db_init_db()
        assert get_message_count() == 0


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeCompletion:
    choices: list[_FakeChoice]


class TestStatusGenerator:
    def test_truncates_long_output(self) -> None:
        async def _fake_create(**kwargs: Any) -> Any:
            return _FakeCompletion(
                choices=[_FakeChoice(message=_FakeMessage(content="x" * 200))]
            )

        fake_client = mock.AsyncMock()
        fake_client.chat.completions.create = _fake_create

        result = asyncio.run(
            status_generator.generate_status_message(fake_client, mock.MagicMock())
        )
        assert result is not None
        assert len(result) == 128

    def test_returns_none_on_empty_content(self) -> None:
        async def _fake_create(**kwargs: Any) -> Any:
            return _FakeCompletion(
                choices=[_FakeChoice(message=_FakeMessage(content="   "))]
            )

        fake_client = mock.AsyncMock()
        fake_client.chat.completions.create = _fake_create

        result = asyncio.run(
            status_generator.generate_status_message(fake_client, mock.MagicMock())
        )
        assert result is None

    def test_returns_none_on_api_error(self) -> None:
        from openai import APIError

        fake_request = mock.MagicMock()

        async def _fake_create(**kwargs: Any) -> Any:
            raise APIError("Rate limited", request=fake_request, body={})

        fake_client = mock.AsyncMock()
        fake_client.chat.completions.create = _fake_create

        result = asyncio.run(
            status_generator.generate_status_message(fake_client, mock.MagicMock())
        )
        assert result is None
