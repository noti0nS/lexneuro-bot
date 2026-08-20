import logging

logger = logging.getLogger(__name__)
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import override


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.end_headers()

    @override
    def log_message(self, format: str, *args: object) -> None:
        pass


def start_health_server() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health check server listening on port %d", port)
