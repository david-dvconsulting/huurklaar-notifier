"""`--selftest`: controleert de kern tegen een nep-server, zonder GUI, Keychain of netwerk buiten localhost."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from ..testing.fake_server import EMPTY, FAKE_KEY, FakeServer
from ..testing.fakes import FakePlatform
from .controller import Controller
from .i18n import CATALOG, LANGUAGES
from .menu import build_menu
from .state import Status


def run(output: str | None = None) -> int:
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    keys = [set(CATALOG[lang]) for lang in LANGUAGES]
    check(all(k == keys[0] for k in keys), "vertaalsleutels verschillen per taal")

    with FakeServer() as server, tempfile.TemporaryDirectory() as tmp:
        c = Controller(FakePlatform(Path(tmp)))
        check(c.poll() == [] and c.state.status is Status.NOT_CONFIGURED, "niet aangemeld")
        c.configure(server.url, FAKE_KEY)
        toasts = c.poll()
        check(c.state.status is Status.ATTENTION and len(toasts) == 1, "taken en één melding")
        check(c.poll() == [], "dezelfde melding niet twee keer")
        for lang in LANGUAGES:
            check(len(build_menu(c.state, lang, "auto", False)) > 5, f"menu in {lang}")
        server.body = EMPTY
        c.poll()
        check(c.state.status is Status.IDLE, "niets te doen")
        server.status = 500
        c.poll()
        check(c.state.status is Status.OFFLINE, "serverfout is geen verbinding")
        c.platform.secrets.set("hkn_andere_sleutel_enkel_test")
        c.poll()
        check(c.state.status is Status.AUTH_FAILED and c.next_delay() is None, "ongeldige sleutel")

    if sys.platform == "win32":
        from ..platform import windows_selftest

        windows_selftest.run(check)

    lines = [f"MISLUKT: {p}" for p in problems]
    lines.append("selftest: OK" if not problems else f"selftest: {len(problems)} probleem(en)")
    # Een --noconsole-exe heeft geen stdout: print() doet dan niets, dus ook naar een bestand schrijven.
    if sys.stdout is not None:
        print("\n".join(lines))
    if output:
        Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if problems else 0
