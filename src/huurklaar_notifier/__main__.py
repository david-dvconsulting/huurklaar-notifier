"""Startpunt: `python -m huurklaar_notifier` of de gebundelde app."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="huurklaar-notifier")
    parser.add_argument("--selftest", action="store_true", help="controleer de kern zonder GUI")
    parser.add_argument(
        "--selftest-output",
        metavar="BESTAND",
        help="schrijf de uitkomst van --selftest ook naar dit bestand (een --noconsole-exe heeft geen stdout)",
    )
    parser.add_argument("--version", action="store_true")
    parser.add_argument(
        "--forget", action="store_true", help="Windows: ruim sleutel en autostart op (uninstall)"
    )
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.selftest:
        from .core.selftest import run

        return run(args.selftest_output)
    if sys.platform == "darwin":
        from .platform.macos import run as run_mac

        run_mac()
        return 0
    if sys.platform == "win32":
        if args.forget:
            from .platform.windows import forget

            return forget()
        from .platform.windows import run as run_windows

        return run_windows()
    print("Dit platform wordt niet ondersteund.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
