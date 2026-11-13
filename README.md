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

## Indeling

- `core/`: API-client, toestanden en back-off, menu-model, vertalingen (nl/fr/en), controller en poller. Importeert geen GUI.
- `platform/`: per platform de sleutelopslag (`keyring`), meldingen, menubalk of tray en 'start bij aanmelden'. Nu `macos.py`.
- `testing/`: nep-server en nep-platform, ook gebruikt door `--selftest`.
- `prototype/`: het meldingsprototype waarmee de keuze voor `UNUserNotificationCenter` is gemaakt.

## Eerste start op een Mac

De app is ad hoc ondertekend (gratis, geen Apple Developer-account). Gatekeeper meldt dat één keer: kies **Toch openen** in Systeeminstellingen > Privacy en beveiliging.
