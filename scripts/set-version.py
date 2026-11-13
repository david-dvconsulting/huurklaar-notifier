"""Zet de versie van de app op die van een tag: de tag is de enige bron van waarheid.

Gebruik: python scripts/set-version.py v1.2.3        (schrijft src/huurklaar_notifier/_version.py)
         python scripts/set-version.py v1.2.3 --check  (controleert enkel, schrijft niets)

Toegestane tags: `vX.Y.Z` (release) en `vX.Y.Z-rc.N` (voorversie, wordt een prerelease en door de
updatecheck genegeerd). Alles anders stopt de build vóór er iets gebouwd wordt.
Op GitHub Actions schrijft het script ook `version` en `prerelease` naar $GITHUB_OUTPUT.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

TAG = re.compile(r"^v(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?P<rc>-rc\.[1-9]\d*)?)$")
TARGET = Path(__file__).resolve().parents[1] / "src" / "huurklaar_notifier" / "_version.py"


def version_from_tag(tag: str) -> tuple[str, bool]:
    """Geeft (versie zonder v, is_prerelease) of werpt een ValueError."""
    match = TAG.match(tag)
    if not match:
        raise ValueError(f"tag {tag!r} heeft niet de vorm vX.Y.Z of vX.Y.Z-rc.N")
    return match["version"], bool(match["rc"])


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        version, pre = version_from_tag(args[0])
    except ValueError as e:
        print(f"FOUT: {e}", file=sys.stderr)
        return 1
    if "--check" not in argv:
        TARGET.write_text(
            '"""Gegenereerd door scripts/set-version.py vanuit de releasetag; niet met de hand aanpassen."""\n\n'
            f'__version__ = "{version}"\n',
            encoding="utf-8",
        )
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"version={version}\nprerelease={'true' if pre else 'false'}\n")
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
