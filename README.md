# Huurklaar Meldingen

Menubalk-app (Mac) en tray-app (Windows, KAN-120) die meldingen geeft bij taken en vereiste acties van Huurklaar (KAN-117). Eén Python-codebasis. De app praat met de Huurklaar-API via een alleen-lezen **meldingssleutel** (`GET /me/notifications`, zie `docs/meldingen.md` in de Huurklaar-repo).

> Deze repo is publiek: zet nooit een echte sleutel, adres van een klant of persoonsgegevens in code, tests of fixtures. De tests gebruiken verzonnen gegevens (`testing/fake_server.py`).

## Instellen

Kies **Instellingen…** in het menu: vul het **adres van de Huurklaar-API** in (bv. dev: zie `docs/developer_info.md` in de Huurklaar-repo; lokaal `http://localhost:3000`) en de **meldingssleutel** (Huurklaar > Mijn profiel > Meldingen). Het adres staat in `~/Library/Application Support/Huurklaar Meldingen/config.json`; de sleutel enkel in de Keychain en nooit in een bestand of log. Alleen `https` is toegestaan, behalve voor localhost.

## Ontwikkelen

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[mac,dev]"
.venv/bin/pytest            # tests (geen GUI nodig)
.venv/bin/ruff check . && .venv/bin/ruff format .
.venv/bin/python -m huurklaar_notifier --selftest
.venv/bin/python -m huurklaar_notifier   # de app zelf (Mac)
scripts/build-mac.sh        # .app + .dmg in dist/ (ad hoc ondertekend)
```

Een release maken, de versieconventie, de proefrun en de updatecheck: zie [docs/bouwen-en-releasen.md](docs/bouwen-en-releasen.md).

## Indeling

- `core/`: API-client, toestanden en back-off, menu-model, vertalingen (nl/fr/en), controller en poller. Importeert geen GUI.
- `platform/`: per platform de sleutelopslag (`keyring`), meldingen, menubalk of tray en 'start bij aanmelden'. `macos.py` en, voor Windows, `windows.py` (alleen daar te importeren) met de testbare logica in `windows_registry.py`, `windows_notifier.py`, `windows_icon.py` en `windows_menu.py`.
- `testing/`: nep-server en nep-platform, ook gebruikt door `--selftest`.
- `prototype/`: het meldingsprototype waarmee de keuze voor `UNUserNotificationCenter` is gemaakt.

## Eerste start op een Mac

De app is ad hoc ondertekend (gratis, geen Apple Developer-account). Gatekeeper meldt dat één keer: kies **Toch openen** in Systeeminstellingen > Privacy en beveiliging.

## Windows (KAN-120)

**Instellen**: kies in het tray-menu **Instellingen…**. Adres en sleutel staan in één venster; het adres in `%APPDATA%\Huurklaar Meldingen\config.json`, de sleutel enkel in de **Windows Credential Manager** (nooit in een bestand of log).

**Hoe het werkt**
- Tray met `pystray`; het icoon is het logo met een badge: teller (oranje, rood bij te late taken), `!` (niet aangemeld of sleutel ongeldig), grijze stip (geen verbinding), geen badge (niets te doen).
- Meldingen met `win11toast` onder de **AppUserModelID** `be.huurklaar.meldingen`, geregistreerd onder `HKCU\Software\Classes\AppUserModelId` (naam en icoon), zodat niet 'Python' verschijnt. Een klik opent het adres rechtstreeks via Windows (protocol-toast): we wachten op niets en houden geen thread per melding open.
- 'Start bij aanmelden': waarde `HuurklaarMeldingen` onder `HKCU\...\Run` (enkel de huidige gebruiker, geen beheerdersrechten). De installer schrijft dezelfde waarde.
- Eén exemplaar tegelijk (benoemde mutex, ook gebruikt door de installer).

**Bouwen (op Windows, PowerShell)**

```powershell
py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
scripts\build-windows.ps1 -Version 0.1.0     # of -SkipInstaller zonder Inno Setup
```

Het script doet de self-test vóór het bouwen en in elke gebouwde `.exe` (met time-out), en levert `dist\Huurklaar-Meldingen.exe` (één bestand) en `dist\Huurklaar-Meldingen-Setup-<versie>.exe` (Inno Setup 6, gratis; installeert in `%LOCALAPPDATA%\Programs`, zonder beheerdersrechten, met Start-menu-item, de optie 'start bij aanmelden' en een nette uninstall die ook de bewaarde sleutel wist). De installer gebruikt een map (`--onedir`), niet het ene bestand: sneller bij het starten en minder kans op een valse virusmelding. CI: `.github/workflows/windows-build.yml` is een bouwsteen; publiceren hoort bij KAN-121.

**Eerste start (SmartScreen)**: de `.exe` en de installer zijn niet ondertekend (geen betaald certificaat). Windows toont eenmalig 'Windows heeft uw pc beschermd'. Kies **Meer info** en dan **Toch uitvoeren**. Een melding van een virusscanner is dan een vals alarm; zie `docs`-notities van KAN-122.
