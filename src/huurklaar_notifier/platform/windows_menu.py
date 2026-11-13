"""Vertaalt het platformonafhankelijke menu-model naar pystray-items. De klassen worden aangereikt, zodat dit
zonder Windows (en zonder pystray) getest wordt."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.menu import Entry

MAX_TOOLTIP = 127  # Windows kapt de tooltip van een tray-icoon daar af


def build_items(
    entries: list[Entry],
    make_item: Callable[..., Any],
    make_menu: Callable[..., Any],
    separator: Any,
    on_entry: Callable[[Entry], None],
) -> list[Any]:
    out: list[Any] = []
    for e in entries:
        if e.separator:
            out.append(separator)
        elif e.children:
            out.append(
                make_item(
                    e.label,
                    make_menu(*build_items(list(e.children), make_item, make_menu, separator, on_entry)),
                )
            )
        else:
            actionable = e.enabled and bool(e.url or e.action)
            out.append(
                make_item(
                    e.label,
                    _action(e, on_entry) if actionable else None,
                    checked=None if e.checked is None else _checked(e.checked),
                    enabled=actionable,
                )
            )
    return out


# pystray telt de parameters van een actie (hoogstens twee, `icon` en `item`) en weigert er meer:
# daarom losse fabrieken in plaats van een lambda met een extra standaardwaarde.
def _action(entry: Entry, on_entry: Callable[[Entry], None]) -> Callable[[Any, Any], None]:
    def run(icon: Any, item: Any) -> None:
        on_entry(entry)

    return run


def _checked(value: bool) -> Callable[[Any], bool]:
    def get(item: Any) -> bool:
        return value

    return get


def tooltip(status_line: str, app_name: str) -> str:
    text = f"{app_name}: {status_line}"
    return text if len(text) <= MAX_TOOLTIP else text[: MAX_TOOLTIP - 1] + "…"
