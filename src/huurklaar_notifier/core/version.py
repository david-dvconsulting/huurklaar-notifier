"""Versies lezen en vergelijken (semver) voor de updatecheck: `1.10` > `1.9`, een voorloper-`v` mag,
een prerelease (`1.2.0-rc.1`) is ouder dan de release (`1.2.0`) en bouwmetadata (`+abc`) telt niet mee."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(
    r"^[vV]?(?P<release>\d{1,9}(?:\.\d{1,9}){0,2})"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@dataclass(frozen=True, slots=True)
class Version:
    release: tuple[int, int, int]
    pre: tuple[str, ...] = ()  # leeg = een echte release

    @property
    def is_prerelease(self) -> bool:
        return bool(self.pre)

    def __str__(self) -> str:
        base = ".".join(str(n) for n in self.release)
        return base + ("-" + ".".join(self.pre) if self.pre else "")

    def _key(self) -> tuple:
        # Semver: een release staat boven zijn prereleases; numerieke delen staan onder tekstdelen.
        pre = (
            (1,) if not self.pre else (0, *((0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.pre))
        )
        return (self.release, pre)

    def __lt__(self, other: Version) -> bool:
        return self._key() < other._key()


def parse_version(text: str) -> Version:
    match = _PATTERN.match(text.strip())
    if not match:
        raise ValueError(f"geen geldige versie: {text!r}")
    nums = [int(p) for p in match["release"].split(".")]
    nums += [0] * (3 - len(nums))
    pre = tuple(match["pre"].split(".")) if match["pre"] else ()
    return Version((nums[0], nums[1], nums[2]), pre)


def is_newer(candidate: str, current: str) -> bool:
    """Waar als `candidate` strikt nieuwer is. Een ongeldige versie is nooit nieuwer (nooit een foute melding)."""
    try:
        return parse_version(current) < parse_version(candidate)
    except ValueError:
        return False
