"""Een nep-API met verzonnen gegevens, voor tests en `--selftest`. Bevat geen echte sleutel of persoon."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

FAKE_KEY = "hkn_fake_key_enkel_voor_tests"

SAMPLE: dict[str, Any] = {
    "generatedAt": "2026-11-13T10:00:00.000Z",
    "pollAfterSeconds": 900,
    "locale": "nl",
    "enabled": True,
    "counts": {"total": 2, "overdue": 1, "actionRequired": 1},
    "accounts": [{"accountId": "a1", "name": "Voorbeeld Verhuur", "total": 2, "overdue": 1}],
    "items": [
        {
            "id": "task-1",
            "kind": "task",
            "title": "Indexatie nakijken",
            "accountName": "Voorbeeld Verhuur",
            "propertyLabel": "Teststraat 1",
            "status": "open",
            "dueDate": "2026-11-01",
            "overdue": True,
            "actionRequired": True,
            "href": "https://app.example.test/tasks/task-1",
        },
        {
            "id": "task-2",
            "kind": "complaint",
            "title": "Lekkage",
            "overdue": False,
            "actionRequired": False,
            "href": "https://app.example.test/tasks/task-2",
        },
    ],
    "truncated": False,
}
EMPTY: dict[str, Any] = {**SAMPLE, "counts": {"total": 0, "overdue": 0, "actionRequired": 0}, "items": []}


class FakeServer:
    """Antwoordt op `GET /me/notifications`; `body` en `status` kunnen per test aangepast worden."""

    def __init__(self) -> None:
        self.body: Any = SAMPLE
        self.status = 200
        self.requests: list[dict[str, str | None]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization")})
                ok = (
                    self.path == "/me/notifications"
                    and self.headers.get("Authorization") == f"Bearer {FAKE_KEY}"
                )
                code = outer.status if ok else 401
                payload = json.dumps(outer.body if code == 200 else {"error": "unauthorized"}).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:  # geen logregels met headers
                pass

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_port}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def __enter__(self) -> FakeServer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
