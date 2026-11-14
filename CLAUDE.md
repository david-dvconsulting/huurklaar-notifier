# Huurklaar Meldingen (huurklaar-notifier)

Menubalk-app (Mac) en tray-app (Windows) in één Python 3.13-codebase. De app vraagt `GET /me/notifications` op bij de Huurklaar-API met een alleen-lezen meldingssleutel. Setup, ontwikkelen en releases staan in `README.md` (Engels), versies en builds in `docs/bouwen-en-releasen.md`.

**Deze repo is publiek.** Zet nooit een echte sleutel, een klantadres of persoonsgegevens in code, tests, fixtures, commitberichten of PR-teksten. Tests gebruiken verzonnen data: `SAMPLE` in `src/huurklaar_notifier/testing/fake_server.py`.

## Commando's

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -e ".[mac,dev]"   # of: python3 -m venv .venv && .venv/bin/pip install -e ".[mac,dev]"
```

Verificatie, dezelfde stappen als CI. Draai ze vóór je zegt dat iets klaar is:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q && .venv/bin/python -m huurklaar_notifier --selftest
```

- **In een worktree** hergebruik je de `.venv` van de hoofdkopie. `pytest` test dankzij `pythonpath = ["src"]` al de eigen code. De selftest heeft `PYTHONPATH=src` nodig, anders draait de geïnstalleerde kopie uit de hoofdmap:
  `PYTHONPATH=src ../../huurklaar-notifier/.venv/bin/python -m huurklaar_notifier --selftest`
- **CI** (`.github/workflows/ci.yml`) draait lint, tests en selftest op `windows-latest` én `macos-latest`. `platform/windows.py` kan lokaal op een Mac niet draaien: houd Windows-logica testbaar in `platform/windows_*.py` en denk aan Windows-verschillen (bestandsvergrendeling, `os.replace` die faalt als een ander proces of een andere thread het doel vasthoudt).

## Architectuur

- `core/` importeert nooit een GUI.
  - `api.py`: HTTP-client.
  - `models.py`: `parse_snapshot` blijft bewust tolerant voor nieuwe velden.
  - `state.py`: `State` met statussen, back-off (`BACKOFF_MAX`) en de `seen`-logica (`_new_toasts`, `MAX_SEEN`).
  - `controller.py`: `Controller` met `_lock`, `poll`, `configure` en `set_language`.
  - `poller.py`: `Poller` en `UpdatePoller`, elk op een eigen thread.
  - `menu.py`: `build_menu` en `kind_label`.
  - `i18n.py`: catalogus in NL, FR en EN, met NL als bron.
  - `config.py`: `ConfigStore` schrijft atomair weg.
  - Verder: `updates.py`, `tls.py`, `version.py`, `selftest.py`.
- `platform/` bevat per platform de sleutelopslag, de meldingen, de menubalk of tray en "start bij aanmelden".
  - `macos.py`: rumps. `MenubarApp._tick` draait elke seconde op de hoofdthread.
  - `windows.py`: alleen importeerbaar op Windows. `TrayApp._loop` draait op een eigen thread.
- `testing/` bevat de nep-server, nep-GitHub en het nep-platform. De tests en `--selftest` gebruiken ze allebei.

## Threads: lees dit vóór je toestand of config aanraakt

- Drie threads raken dezelfde toestand: de poll-thread (`Poller`), de updatecheck-thread (`UpdatePoller`) en de UI (rumps-timer op de Mac, tray-thread op Windows).
- Alles wat `controller.config` of `controller.state` wijzigt of de config wegschrijft, gebeurt onder `Controller._lock`. `ConfigStore.save` neemt daarnaast een eigen lock.
- **Geen enkele lus mag stoppen door een onverwachte fout.** Zet een `try/except Exception` rond de lusbody, log enkel `type(e).__name__` en probeer later opnieuw. Zet `_rebuild_needed` pas op `False` nadat `_render()` gelukt is.
- Tests met threads wachten altijd met een time-out (`Event.wait(timeout=2)`) en stoppen de thread op het einde (`stop()` plus `join(timeout=...)`). Maak wachttijden instelbaar via een constructorparameter met een standaardwaarde, zodat de test snel blijft.
- Een concurrency-test moet falen op de oude code. Controleer dat eenmalig.

## Compatibel blijven met de server

- Al geïnstalleerde versies kunnen we niet meer aanpassen, dus de app moet nieuwe velden en waarden van de server verdragen.
  - Een onbekende `kind` toont "Melding" (`kind.other`).
  - `translate` geeft bij een ontbrekende sleutel de sleutel zelf terug.
  - Een fout in het menu mag het pollen nooit stoppen.
- De server stuurt hoogstens 50 items, gesorteerd op dringendheid. Zijn er meer, dan staat `truncated: true` in het antwoord. `seen` bewaart in dat geval ook ids die buiten de lijst vallen, anders volgen er dubbele meldingen.

## Conventies

- **Taal**: commentaar, docstrings, testnamen, UI-teksten en commitberichten in het Nederlands. Identifiers in het Engels. De README is in het Engels.
- **Stijl**: ruff met regelbreedte 110 en de regels E, F, I, UP, B en SIM. Commentaar legt het *waarom* uit.
- **UI-tekst**: zet elke nieuwe sleutel in NL, FR en EN in `core/i18n.py`. Een test bewaakt dat alle talen dezelfde sleutels hebben.
- **Logs**: nooit een sleutel, titel, adres of ander gegeven. Enkel het fouttype.
- **Werkwijze per Jira-ticket**: één branch `kan-<taak>-<korte-omschrijving>` en één PR per taak, met één commit per sub-task. Een commit heet `KAN-<sub-task>: <wat>` en legt in de body het waarom uit. De volledige werkwijze staat in de skill `kan-ticket` in de app-repo (`huurklaar/.claude/skills/kan-ticket/SKILL.md`). Zet geen interne links (Jira-site) in PR-teksten, want de repo is publiek.
- **Git-identiteit**: commits staan op `david <david@dvconsulting.be>`, ingesteld in de repo-config (`git config user.email`). Is de globale git-config een ander adres, zet de identiteit dan per repo. Controleer de auteur met `git log -1 --format='%an <%ae>'` vóór je pusht: deze repo is publiek.
- **Releases**: zie de README en `scripts/release.sh`. Verplaats of hergebruik nooit een tag. Een release maak je alleen op uitdrukkelijk verzoek.
