# Bouwen en releasen

Voor wie lokaal wil bouwen of een nieuwe versie wil uitbrengen. Alles is gratis: de repo is publiek, dus GitHub Actions kost niets en releases zijn zonder aanmelding leesbaar. Er zijn geen secrets nodig.

## De versie: de tag is de bron

- Een release heet `vX.Y.Z` (bv. `v1.2.0`). Een voorversie heet `vX.Y.Z-rc.N` (bv. `v1.2.0-rc.1`) en wordt een *prerelease*; de updatecheck negeert die.
- De tag staat los van de `vX.Y.Z`-tags van de Huurklaar-app zelf (andere repo, eigen reeks, begint bij `v0.1.0`).
- `scripts/set-version.py <tag>` schrijft het nummer in `src/huurklaar_notifier/_version.py`. Dat bestand bevat in git altijd de placeholder `0.0.0` (ouder dan elke release); alleen de build vult het in. Zo staat het nummer nergens op twee plaatsen.
- Een tag die niet de vorm `vX.Y.Z` of `vX.Y.Z-rc.N` heeft, stopt de workflow vóór er iets gebouwd wordt (`python3 scripts/set-version.py <tag> --check` probeert het lokaal).
- Daarna controleert de workflow in het gebouwde pakket dat de app hetzelfde nummer meldt (`--version`, `Info.plist`).

## Een release maken

1. Zorg dat `main` groen is en alles bevat wat erin moet.
2. Start in IntelliJ de run-config **Release maken (tag op main)** (`scripts/release.sh`). Het script controleert dat je op een schone, bijgewerkte `main` staat, vraagt eerst of het een minor of major is (geen antwoord binnen 10 s = patch), toont de nieuwe versie, vraagt bevestiging en pusht de tag. Een eigen versie of voorversie kan met `scripts/release.sh v1.2.0-rc.1`. De vragen Minor en Major stelt het script zelf (`--ask`); het toont daarna 'Soort release: patch (v0.3.0 wordt v0.3.1)' en vraagt bevestiging. Met de hand kan ook (dit start de workflow `Release`):

   ```bash
   git checkout main && git pull
   git tag v1.2.0
   git push origin v1.2.0
   ```

3. Volg de run onder **Actions**. De workflow:
   1. controleert de tag, dat hij op `main` staat en dat er nog geen release met die naam bestaat;
   2. bouwt op `macos-latest` de `.dmg` (ad hoc ondertekend) en op `windows-latest` de `.exe` en `setup.exe`; elke job draait eerst lint, tests en `--selftest`, en daarna `--selftest` en een versiecontrole in het gebouwde pakket;
   3. publiceert alles in **één** release met `gh release create --generate-notes` (de releasenotes komen uit de gemergede pull requests en commits).
4. Controleer de release op de releasepagina en pas zo nodig de notities aan.

Een foute release herstel je door een nieuwe, hogere versie uit te brengen. Gebruik een release niet opnieuw: de updatecheck vergelijkt versienummers.

## Proefrun zonder te publiceren

Onder **Actions > Release > Run workflow** kies je een tag-naam (bv. `v0.0.1-rc.1`). De workflow bouwt en test alles maar publiceert niets; de bestanden staan 7 dagen als artefact bij de run. Er wordt geen tag of release aangemaakt.

## Vastgepinde afhankelijkheden in releases

`pyproject.toml` bevat enkel ondergrenzen (`keyring>=25`, ...). Zonder lock bundelt elke release de nieuwste versie die PyPI op dat moment heeft: een gecompromitteerd of kapot pakket zou zo ongemerkt in een niet-ondertekende `.dmg` of `.exe` belanden, en een release is niet reproduceerbaar. Daarom installeert `release.yml` uit lockbestanden met exacte versies en hashes:

- `requirements/release-mac.txt` (Python 3.13, `aarch64-apple-darwin`) en `requirements/release-windows.txt` (Python 3.13, `x86_64-pc-windows-msvc`), elk met de extra's van het platform plus `dev` (PyInstaller, ruff, pytest) en met alle indirecte afhankelijkheden.
- `requirements/release-build.in` voegt `setuptools` toe, de build-backend van het project. Zo hoeft `pip install --no-build-isolation` niets zonder hash van PyPI te halen.
- De workflow doet `pip install --require-hashes -r requirements/release-<platform>.txt` en daarna `pip install --no-deps --no-build-isolation -e .`. `scripts/build-windows.ps1` krijgt in de release `-SkipInstall`, anders installeert het script nog eens zonder hashes. Lokaal (zonder die schakelaar) werkt het script zoals voorheen.
- Het Mac-lock is voor Apple Silicon omdat `macos-latest` dat is en `scripts/build-mac.sh` voor de eigen architectuur bouwt (geen universal2). Wil je later Intel of universal2 ondersteunen, dan hoort daar een eigen lock bij.
- De **gewone CI (`ci.yml`) gebruikt bewust de ranges** uit `pyproject.toml`: zo merk je vroeg dat een nieuwe versie iets breekt, ook als de release nog op de oude versie staat.
- Dependabot (`.github/dependabot.yml`, ecosystem `pip`, map `/requirements`, wekelijks) stelt updates van de locks voor als pull request. Omdat `ci.yml` de locks niet gebruikt, test `.github/workflows/release-locks.yml` ze apart: bij elke wijziging aan `requirements/**` of `pyproject.toml` installeert die workflow de lock op Mac en Windows zoals de release dat doet, en draait hij `pip check`, de tests en de self-test. Controleer in een Dependabot-PR dat de hashes mee bijgewerkt zijn; lukt dat niet, vernieuw het lock dan zelf (hieronder).
- Niet gedekt: Inno Setup, dat de Windows-job via Chocolatey installeert.

**Keuze: uv** (niet pip-tools). uv lost voor een ander doelplatform op, dus beide locks maak je vanaf één machine; pip-tools lost enkel op voor het platform waarop het draait, zodat de Windows-lock op Windows gemaakt zou moeten worden. De locks zelf zijn gewone requirements-bestanden: de workflows installeren ze met pip, zonder uv.

Locks vernieuwen (vereist [uv](https://docs.astral.sh/uv/)):

```bash
scripts/lock-release.sh                              # alles naar de nieuwste toegelaten versies
scripts/lock-release.sh --upgrade-package keyring    # of enkel één pakket
```

Het script draait `uv pip compile pyproject.toml requirements/release-build.in --extra <mac|windows> --extra dev --generate-hashes --python-version 3.13 --python-platform <aarch64-apple-darwin|x86_64-pc-windows-msvc> -o requirements/release-<platform>.txt`. Commit de gewijzigde lockbestanden en doe een proefrun (zie hierboven) vóór je een tag zet. Verander je de afhankelijkheden in `pyproject.toml`, vernieuw dan ook de locks.

## Bestandsnamen

De release bevat bestanden met een vaste naam, zonder versie, zodat `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest/download/<naam>` altijd naar de nieuwste versie wijst:

| Bestand | Wat |
|---|---|
| `Huurklaar-Meldingen.dmg` | Mac (ad hoc ondertekend) |
| `Huurklaar-Meldingen-Setup.exe` | Windows-installer (Inno Setup): Start-menu, 'start bij aanmelden', nette verwijdering. Aanbevolen. |
| `Huurklaar-Meldingen.exe` | Windows, één los bestand, zonder installatie (proberen of op een pc waar je niets mag installeren) |
| `SHA256SUMS.txt` | controlesommen van de bestanden hierboven |

De releasepagina zelf is `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest`.

## Lokaal bouwen

Python 3.13 is nodig.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[mac,dev]"          # Windows: ".[windows,dev]"; dit gebruikt de ranges, niet de release-locks
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
.venv/bin/python -m huurklaar_notifier --selftest
scripts/build-mac.sh                            # .app en .dmg in dist/
```

`scripts/build-mac.sh` accepteert een versie als argument (`scripts/build-mac.sh 1.2.0`); zonder argument gebruikt het `_version.py`. Wil je lokaal een versie testen zoals de CI, voer dan eerst `python3 scripts/set-version.py v1.2.0` uit en zet daarna `_version.py` terug met `git checkout src/huurklaar_notifier/_version.py`.

Windows (PowerShell, Python 3.13 en Inno Setup 6): `scripts\build-windows.ps1 -Version 1.2.0`. Het script installeert de afhankelijkheden, draait de self-test, bouwt `dist\Huurklaar-Meldingen.exe` en `dist\Huurklaar-Meldingen-Setup-<versie>.exe` en test de `.exe`'s zelf. In de release krijgen ze de vaste namen uit de tabel hierboven.

## De updatecheck

De app vraagt eens per dag `https://api.github.com/repos/david-dvconsulting/huurklaar-notifier/releases/latest` op, zonder login, met een time-out van 5 seconden en `User-Agent: HuurklaarMeldingen/<versie>`.

- Het tijdstip van de volgende check staat in `config.json` (datamap van de app) en blijft dus na een herstart bewaard. Na een mislukte check proberen we het na een uur opnieuw; bij een bereikte limiet (GitHub staat 60 aanvragen per uur per IP toe) na zes uur.
- Mislukken is altijd stil: offline, time-out, limiet, 404 of ongeldige JSON geven nooit een melding of crash.
- Drafts, prereleases en tags die geen gewone `vX.Y.Z` zijn, worden genegeerd. De vergelijking is semantisch (`1.10` is hoger dan `1.9`).
- Bij een nieuwere versie toont het menu **Nieuwe versie vX.Y.Z** (nl/fr/en). Een klik opent de releasepagina. Automatisch vervangen van de app is een latere stap.
- De link naar de releasepagina bouwt de app zelf uit de tag; ze neemt geen adres uit het antwoord over.

Proberen op je eigen Mac: een lokale build heeft versie `0.0.0` en toont dus 'Nieuwe versie' zodra er een release bestaat.

## Reserve: installers op S3

Als GitHub ooit niet volstaat, kunnen de installers per versie op S3 komen, via de uitrol van de Huurklaar-repo (`scripts/deploy-app.sh`-stijl). Dat is niet gebouwd; het wordt enkel uitgewerkt op verzoek.
