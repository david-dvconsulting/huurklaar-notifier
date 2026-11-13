"""Versievergelijking (voor de updatecheck van KAN-121): `1.2.10` > `1.2.9`, een voorloper-`v` mag."""

from __future__ import annotations


def parse_version(text: str) -> tuple[int, ...]:
    parts = text.strip().lstrip("vV").split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        raise ValueError(f"geen geldige versie: {text!r}") from None


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))
