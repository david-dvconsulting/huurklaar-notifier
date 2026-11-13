"""Het antwoord van `GET /me/notifications` (KAN-118, `packages/shared/src/notifications.ts`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ProtocolError(Exception):
    """Het antwoord heeft niet de afgesproken vorm."""


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    kind: str
    title: str
    account_name: str | None
    property_label: str | None
    status: str | None
    due_date: str | None
    overdue: bool
    action_required: bool
    href: str


@dataclass(frozen=True, slots=True)
class Snapshot:
    generated_at: str
    poll_after_seconds: int
    locale: str
    enabled: bool
    total: int
    overdue: int
    action_required: int
    items: tuple[Item, ...]
    truncated: bool


def _str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str):
        raise ProtocolError(f"veld {key} ontbreekt of is geen tekst")
    return v


def _opt_str(d: dict[str, Any], key: str) -> str | None:
    v = d.get(key)
    return v if isinstance(v, str) and v else None


def _bool(d: dict[str, Any], key: str) -> bool:
    v = d.get(key)
    if not isinstance(v, bool):
        raise ProtocolError(f"veld {key} ontbreekt of is geen boolean")
    return v


def _int(d: dict[str, Any], key: str) -> int:
    v = d.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        raise ProtocolError(f"veld {key} ontbreekt of is geen getal")
    return v


def _item(raw: object) -> Item:
    if not isinstance(raw, dict):
        raise ProtocolError("een item is geen object")
    return Item(
        id=_str(raw, "id"),
        kind=_str(raw, "kind"),
        title=_str(raw, "title"),
        account_name=_opt_str(raw, "accountName"),
        property_label=_opt_str(raw, "propertyLabel"),
        status=_opt_str(raw, "status"),
        due_date=_opt_str(raw, "dueDate"),
        overdue=_bool(raw, "overdue"),
        action_required=_bool(raw, "actionRequired"),
        href=_str(raw, "href"),
    )


def parse_snapshot(data: object) -> Snapshot:
    """Valideert het antwoord; onbekende velden negeren we zodat de server uitbreidbaar blijft."""
    if not isinstance(data, dict):
        raise ProtocolError("het antwoord is geen object")
    counts = data.get("counts")
    items = data.get("items")
    if not isinstance(counts, dict) or not isinstance(items, list):
        raise ProtocolError("counts of items ontbreekt")
    return Snapshot(
        generated_at=_str(data, "generatedAt"),
        poll_after_seconds=_int(data, "pollAfterSeconds"),
        locale=_str(data, "locale"),
        enabled=_bool(data, "enabled"),
        total=_int(counts, "total"),
        overdue=_int(counts, "overdue"),
        action_required=_int(counts, "actionRequired"),
        items=tuple(_item(i) for i in items),
        truncated=_bool(data, "truncated"),
    )
