"""Startpunt: `python -m huurklaar_notifier` of de gebundelde app."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="huurklaar-notifier")
    parser.add_argument("--selftest", action="store_true", help="controleer de kern zonder GUI")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.selftest:
        from .core.selftest import run

        return run()
    if sys.platform == "darwin":
        from .platform.macos import run as run_mac

        run_mac()
        return 0
    print("Dit platform wordt nog niet ondersteund (Windows volgt in KAN-120).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
