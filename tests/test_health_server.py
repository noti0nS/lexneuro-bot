import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from src.main import _HealthHandler  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
def health_server() -> Iterator[HTTPServer]:
    server = HTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()


def _get_port(server: HTTPServer) -> int:
    return server.server_address[1]


def test_get_returns_200_with_body(health_server: HTTPServer) -> None:
    conn = HTTPConnection("127.0.0.1", _get_port(health_server))
    conn.request("GET", "/")
    resp = conn.getresponse()
    assert resp.status == 200
    assert resp.read() == b"OK"


def test_head_returns_200_without_body(health_server: HTTPServer) -> None:
    conn = HTTPConnection("127.0.0.1", _get_port(health_server))
    conn.request("HEAD", "/")
    resp = conn.getresponse()
    assert resp.status == 200
    assert resp.read() == b""
