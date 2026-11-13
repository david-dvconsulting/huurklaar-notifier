"""Schrijft het PyInstaller-versiebestand: de .exe krijgt naam, bedrijf en versie in Eigenschappen > Details.

Een .exe zonder die gegevens valt eerder op bij virusscanners en toont een lege bijschrift in Windows.
Gebruik: python scripts/make-version-file.py <versie> <uitvoerbestand>   (versie bv. 1.2.3 of v1.2.3)
"""

import re
import sys
from pathlib import Path

version, out = sys.argv[1].lstrip("vV"), Path(sys.argv[2])
nums = [int(p) for p in re.findall(r"\d+", version.split("-")[0])][:4]
nums += [0] * (4 - len(nums))
tup = tuple(nums)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Huurklaar'),
      StringStruct('FileDescription', 'Huurklaar Meldingen'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'huurklaar-meldingen'),
      StringStruct('OriginalFilename', 'Huurklaar Meldingen.exe'),
      StringStruct('ProductName', 'Huurklaar Meldingen'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
    encoding="utf-8",
)
