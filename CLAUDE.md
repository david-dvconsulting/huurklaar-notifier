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
- **Release-locks**: `release.yml` installeert enkel uit `requirements/release-mac.txt` en `requirements/release-windows.txt` (exacte versies met hashes, gemaakt met uv via `scripts/lock-release.sh`). Wijzig je de afhankelijkheden in `pyproject.toml`, draai dan dat script en commit de locks mee. `.github/workflows/release-locks.yml` test de locks op beide platformen; `ci.yml` gebruikt bewust de ranges.
- **CI** (`.github/workflows/ci.yml`) draait lint, tests en selftest op `windows-latest` én `macos-latest`. `platform/windows.py` kan lokaal op een Mac niet draaien: houd Windows-logica testbaar in `platform/windows_*.py` en denk aan Windows-verschillen (bestandsvergrendeling, `os.replace` die faalt als een ander proces of een andere thread het doel vasthoudt).
- **Lokale Mac-build** (bv. om het URL-schema of een dialoog te testen):
  - In een worktree heeft `scripts/build-mac.sh` een `.venv` nodig. Maak tijdelijk een symlink naar de `.venv` van de hoofdkopie (`.venv` staat in `.gitignore`). De build bundelt dankzij `--paths src` de code van de worktree.
  - Registreer de build met `lsregister -f "<pad>.app"` (`/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister`).
  - De build gebruikt dezelfde bundle-id, Keychain-dienst (`be.huurklaar.meldingen`) en datamap (`~/Library/Application Support/Huurklaar Meldingen`) als een geïnstalleerde app. Kijk vooraf of die bestaan. Ruim nadien op: stop de app, `lsregister -u`, verwijder `build/`, `dist/` en de symlink, en verwijder de datamap en het Keychain-item als je test ze aanmaakte. Of het item van jou is, zie je aan `cdat` in `security find-generic-password -s be.huurklaar.meldingen` (zonder `-w`, dan toont het de sleutel niet).
  - Een osascript-dialoog komt vooraan en neemt het toetsenbord over: een Enter of klik van wie aan de Mac werkt, beantwoordt ze. Zeg dat vooraf, en lees open dialogen met `ps -axo pid,command | grep '[o]sascript'`. `screencapture` werkt niet zonder schermopname-recht. Een dialoog sluiten zonder te bevestigen kan met `pkill -x osascript` (exitcode ≠ 0, dus "geannuleerd").

## Architectuur

- `core/` importeert nooit een GUI.
  - `api.py`: HTTP-client.
  - `models.py`: `parse_snapshot` blijft bewust tolerant voor nieuwe velden.
  - `state.py`: `State` met statussen, back-off (`BACKOFF_MAX`) en de `seen`-logica (`_new_toasts`, `MAX_SEEN`). Een poll geeft een `Delivery(toasts, withdraw)`: de nieuwe meldingen (`Toast` met `key` = item-id en `group` = soort, of `"summary"` voor beide) en de ids die uit `seen` verdwenen zijn. Bij een afgekapte lijst of een fout trekt ze niets in. `missed` telt de meldingen die tijdens een pauze gemist zijn (enkel in het geheugen); `_daily_reminder` maakt de dagelijkse herinnering (sleutel `"reminder"`). De samenvatting na een pauze heeft sleutel `"paused"`; beide hebben groep `"summary"`.
  - `controller.py`: `Controller` met `_lock`, `poll`, `configure`, `set_language` en `test_connection` (één aanvraag met de bewaarde instellingen, zonder toestand of `seen` te wijzigen), en de instellingen uit het menu: `set_pause`/`resume`, `toggle_kind` en `toggle_reminder`. Elk neemt `_lock` en schrijft daarna weg. `next_delay()` wacht nooit langer dan tot het einde van een pauze of tot de volgende 09:00 (`REMINDER_HOUR`), telkens plus 1 s.
  - `poller.py`: `Poller` en `UpdatePoller`, elk op een eigen thread.
  - `menu.py`: `build_menu` groepeert de items per soort (`group_items`, `_distribute` verdeelt de 10 plaatsen round-robin), zet de vervaldatum (`due_label`) en bij meerdere accounts de accountnaam achteraan, en kort labels in met `_fit` (eerst de titel, dan het pand; datum en account blijven heel). `Entry.default` is het standaarditem dat een linksklik op het tray-icoon uitvoert. `title_for` en `title_style` geven de tekst en de kleur (rood bij te laat, Mac) naast het logo. `MenuCache` slaat tekenen over als menu en titel gelijk bleven. Nieuwe parameters van `build_menu` komen als keyword met een standaardwaarde (zoals `base_url`), zodat bestaande aanroepen blijven werken. Instellingen in het menu zijn een prefix-actie (`LANGUAGE_PREFIX`, `PAUSE_PREFIX`, `KIND_PREFIX`) of een vaste actie (`REMINDER`), afgehandeld in `AppActions.handle`. De waarden komen uit `View`, dat de controller onder de lock vult. Het submenu "Meldingen voor" (`kind_entries`) volgt `GROUP_ORDER`.
  - `defaults.py`: het standaard-API-adres (productie) en per bekend API-adres het webadres van de app (`app_url_for`). Verandert het API-domein, pas het dan enkel hier aan.
  - `app_actions.py`: `AppActions`, wat Mac en Windows delen: menuklikken afhandelen (`handle`), de resultatenqueue leeglezen (`drain`), de eerste start (`first_run`: opent de instellingen één keer per proces als adres of sleutel ontbreekt, en leest de sleutelopslag op een eigen thread) en de instellingenflow (`settings`, met een lock zodat er maar één venster tegelijk open staat; na Bewaren test ze de verbinding en toont ze precies één boodschap). Het platform levert enkel een `AppUi` met de dialoog, de alert, het herbouwen en het afsluiten. Kies een foutmelding op exceptietype (`InvalidUrlError`, `InvalidKeyError`, `AuthError`, `NetworkError` uit `api.py`; `AuthError` en `NetworkError` zijn subklassen van `ApiError`, test ze dus eerst), nooit op de fouttekst.
  - `link.py`: `parse_link` en `link_host` voor de koppellink `huurklaar-meldingen://koppel?api=…&key=…` (KAN-267). Een link komt van buiten en is onbetrouwbaar, want elke webpagina kan er een openen. Daarom valideert `parse_link` strikt, en vraagt `AppActions.apply_link` altijd eerst bevestiging met enkel de host (`AppUi.confirm`). Na het koppelen toont ze dezelfde verbindingstest als Bewaren. Een link telt ook als eerste start: `first_run` opent daarna geen instellingenvenster meer, anders verdringt dat venster bij een koude start via de link de koppelvraag. Log nooit de link.
  - `i18n.py`: catalogus in NL, FR en EN, met NL als bron.
  - `config.py`: `ConfigStore` schrijft atomair weg. Elk veld laadt tolerant: een ontbrekende of ongeldige waarde geeft de standaard (`_number`, `_kinds`, `_reminder_flag`, `_date`), want het bestand kan van een oudere versie of met de hand gewijzigd zijn.
  - Verder: `updates.py`, `tls.py`, `version.py`, `selftest.py`.
- `platform/` bevat per platform de sleutelopslag, de meldingen, de menubalk of tray, "start bij aanmelden" en het URL-schema.
  - `base.py`: de protocollen. Een `Notifier` heeft `notify(toast)` en `withdraw(keys)`, en werpt nooit. `drain` trekt eerst in en toont daarna.
  - `macos.py`: rumps. `MenubarApp._tick` draait elke seconde op de hoofdthread. Lees daar nooit de Keychain: dat kan een systeemvenster tonen en de menubalk laten hangen. Houd het dun: wat zonder AppKit kan, staat in een pure module die ook op Windows-CI getest wordt.
    - `MacNotifier` gebruikt `request_id(key)` uit `macos_ids.py` (zonder AppKit, dus ook op Windows testbaar) als id en de groep als `threadIdentifier`.
    - `macos_location.py` (puur): `is_transient_location` (dmg onder `/Volumes/`, App Translocation) en het schrijven en herstellen van de LaunchAgent. Vanaf een tijdelijk pad schrijft "Start bij aanmelden" niets, en `run()` herstelt bij de start een LaunchAgent met een verouderd pad (KAN-287). Enkel gebundeld (`sys.frozen`): in ontwikkeling is `sys.executable` een Python.
    - `settings_dialog.py` (puur) en `macos_settings.py` (AppKit): het instellingenvenster in één NSAlert (KAN-288). AppKit enkel op de hoofdthread: `run_on_main` plant het venster in met `AppHelper.callAfter` en wacht. Alleen het openen heeft een time-out; daarna mag de gebruiker zo lang typen als hij wil. Lukt het venster niet, dan volgt de osascript-terugval.
    - Een app zonder Dock-icoon (`LSUIElement`) krijgt Cmd+V enkel in een tekstveld met een Edit-menu in `NSApp.mainMenu` (`ensure_edit_menu`), en een venster komt enkel vooraan na `activateIgnoringOtherApps_`.
    - `osascript`-dialogen (`alert`, `ask`, `confirm`) blokkeren tot de gebruiker klikt: nooit op de hoofdthread terwijl rumps draait, maar op een daemon-thread.
  - `macos_links.py`: ontvangt de koppellink als Apple Event `kAEGetURL`. De handler staat geregistreerd vóór de run-loop, zodat de link ook bij een koude start aankomt. Het schema staat in de Info.plist (`scripts/build-mac.sh`).
  - `windows.py`: alleen importeerbaar op Windows. `TrayApp._loop` draait op een eigen thread.
  - `windows_notifier.py`: win11toast met `tag` = `toast_tag(key)` (sha1, 32 tekens; Windows staat hoogstens 64 toe) en de vaste groep `"hk"`. `clear_toast` zonder tag wist de hele groep, geef dus altijd een tag mee. win11toast is op de Mac niet geïnstalleerd: lees de API in de bron (`win11toast.py` in de GitHub-repo `GitHub30/win11toast`).
  - `windows_link.py`: Windows start voor een link een nieuw proces. Draait de app al, dan stuurt dat proces de link via een named pipe per gebruiker door. Over die pipe gaan enkel bytes, nooit pickle (`send`/`recv`). Het schema staat onder HKCU: de installer en `register_url_scheme` zetten het, de uninstaller en `--forget` verwijderen het.
- `testing/` bevat de nep-server, nep-GitHub en het nep-platform. De tests en `--selftest` gebruiken ze allebei.

## Threads: lees dit vóór je toestand of config aanraakt

- Drie threads raken dezelfde toestand: de poll-thread (`Poller`), de updatecheck-thread (`UpdatePoller`) en de UI (rumps-timer op de Mac, tray-thread op Windows).
- Alles wat `controller.config` of `controller.state` wijzigt of de config wegschrijft, gebeurt onder `Controller._lock`. `ConfigStore.save` neemt daarnaast een eigen lock.
- **Geen enkele lus mag stoppen door een onverwachte fout.** Zet een `try/except Exception` rond de lusbody, log enkel `type(e).__name__` en probeer later opnieuw. Zet `_rebuild_needed` pas op `False` nadat `_render()` gelukt is.
- Tests met threads wachten altijd met een time-out (`Event.wait(timeout=2)`) en stoppen de thread op het einde (`stop()` plus `join(timeout=...)`). Maak wachttijden instelbaar via een constructorparameter met een standaardwaarde, zodat de test snel blijft.
- Een concurrency-test moet falen op de oude code. Controleer dat eenmalig.

## Tijd: pauze, herinnering en het pollinterval

- Logica die van de klok afhangt, gebruikt de injecteerbare `Controller._clock`, nooit `time.time()`. `State` krijgt geen klok: de controller geeft `paused` en `reminder_day` mee.
- Het pollinterval komt van de server en kan uren duren (de admin standaard 6 u). Iets dat op een vast tijdstip moet gebeuren, begrenst daarom `Controller.next_delay()`. Doe je dat niet, dan komt het tot een interval te laat. Rekenen in lokale tijd doe je met `time.mktime((…, tm_isdst=-1))` (`tomorrow_morning`, `next_local_time`), zodat het zomeruur klopt.
- Tests en `--selftest` die de echte klok gebruiken, krijgen 08:00 lokale tijd (`vroeg_op_de_dag` in `tests/conftest.py`). Anders voegt de herinnering na 9:00 een melding toe en hangt het resultaat af van het uur van de testrun. Verwachtingen leid je af uit `time.localtime`/`time.mktime`, niet uit een vaste tijdzone (CI draait op Windows en macOS).

## Compatibel blijven met de server

- Al geïnstalleerde versies kunnen we niet meer aanpassen, dus de app moet nieuwe velden en waarden van de server verdragen.
  - Een onbekende `kind` toont "Melding" (`kind.other`).
  - `translate` geeft bij een ontbrekende sleutel de sleutel zelf terug.
  - Een fout in het menu mag het pollen nooit stoppen.
- De server stuurt hoogstens 50 items, gesorteerd op dringendheid. Zijn er meer, dan staat `truncated: true` in het antwoord. `seen` bewaart in dat geval ook ids die buiten de lijst vallen, anders volgen er dubbele meldingen.

## Conventies

- **Taal**: commentaar, docstrings, testnamen, UI-teksten en commitberichten in het Nederlands. Identifiers in het Engels. De README is in het Engels.
- **Stijl**: ruff met regelbreedte 110 en de regels E, F, I, UP, B en SIM. Commentaar legt het *waarom* uit.
- **UI-tekst**: zet elke nieuwe sleutel in NL, FR en EN in `core/i18n.py`. Een test bewaakt dat alle talen dezelfde sleutels hebben. De catalogus kent geen meervoudsregels: geef het enkelvoud een eigen sleutel (`toast.paused_summary_one`, `count.task.one`/`count.task.many`), anders staat er "1 nieuwe meldingen".
- **Logs**: nooit een sleutel, titel, adres of ander gegeven. Enkel het fouttype.
- **Menutests**: geef `build_menu` een vaste `today` mee (de vervaldatums in `SAMPLE` liggen in het verleden, dus het label hangt anders af van de dag). Vergelijk je twee menu's na elkaar, geef `Controller` dan ook een vaste `clock`: "Bijgewerkt om HH:MM" staat in het menu en verandert elke minuut.
- **Werkwijze per Jira-ticket**: één branch `kan-<taak>-<korte-omschrijving>` en één PR per taak, met één commit per sub-task. Een commit heet `KAN-<sub-task>: <wat>` en legt in de body het waarom uit. De volledige werkwijze staat in de skill `kan-ticket` in de app-repo (`huurklaar/.claude/skills/kan-ticket/SKILL.md`). Zet geen interne links (Jira-site) in PR-teksten, want de repo is publiek.
- **Git-identiteit**: commits staan op `david <david@dvconsulting.be>`, ingesteld in de repo-config (`git config user.email`). Is de globale git-config een ander adres, zet de identiteit dan per repo. Controleer de auteur met `git log -1 --format='%an <%ae>'` vóór je pusht: deze repo is publiek.
- **Releases**: zie de README en `scripts/release.sh`. Verplaats of hergebruik nooit een tag. Een release maak je alleen op uitdrukkelijk verzoek.
- **Enkel Apple Silicon** (KAN-289, optie C): de Mac-build is arm64 met `LSMinimumSystemVersion` 11.0, en `release.yml` controleert beide. Intel of universal2 invoeren is een nieuwe beslissing; wat er dan moet veranderen, staat in `docs/bouwen-en-releasen.md`. Een build- of workflowwijziging bewijs je met een proefrun van `Release` (workflow_dispatch op de branch, publiceert niets).
