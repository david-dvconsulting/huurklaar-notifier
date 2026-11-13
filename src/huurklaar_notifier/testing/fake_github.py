"""Een nep-GitHub voor de updatecheck, met verzonnen releases. `body`, `status` en `raw` zijn per test instelbaar."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


def release(tag: str, **extra: Any) -> dict[str, Any]:
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": "https://evil.example/x",
        **extra,
    }


class FakeGithub:
    def __init__(self) -> None:
        self.body: Any = release("v1.2.0")
        self.raw: bytes | None = None  # als gezet: dit exacte antwoord (bv. ongeldige JSON)
        self.status = 200
        self.requests: list[dict[str, str | None]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.requests.append(
                    {
                        "path": self.path,
                        "agent": self.headers.get("User-Agent"),
                        "auth": self.headers.get("Authorization"),
                    }
                )
                payload = outer.raw if outer.raw is not None else json.dumps(outer.body).encode()
                self.send_response(outer.status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                pass

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_port}/repos/x/y/releases/latest"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def __enter__(self) -> FakeGithub:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
