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
2. Maak de tag op `main` en push hem (dit start de workflow `Release`):

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

## Bestandsnamen

De release bevat bestanden met een vaste naam, zonder versie, zodat `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest/download/<naam>` altijd naar de nieuwste versie wijst:

| Bestand | Wat |
|---|---|
| `Huurklaar-Meldingen.dmg` | Mac (ad hoc ondertekend) |
| `Huurklaar-Meldingen-Setup.exe` | Windows-installer (Inno Setup) |
| `Huurklaar-Meldingen.exe` | Windows, losse app zonder installatie |
| `SHA256SUMS.txt` | controlesommen van de bestanden hierboven |

De releasepagina zelf is `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest`.

## Lokaal bouwen

Python 3.13 is nodig.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[mac,dev]"          # Windows: ".[windows,dev]"
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
.venv/bin/python -m huurklaar_notifier --selftest
scripts/build-mac.sh                            # .app en .dmg in dist/
```

`scripts/build-mac.sh` accepteert een versie als argument (`scripts/build-mac.sh 1.2.0`); zonder argument gebruikt het `_version.py`. Wil je lokaal een versie testen zoals de CI, voer dan eerst `python3 scripts/set-version.py v1.2.0` uit en zet daarna `_version.py` terug met `git checkout src/huurklaar_notifier/_version.py`.

De Windows-bouwstap staat in `scripts/build-windows.ps1` (KAN-120). Zolang dat bestand ontbreekt, slaat de workflow de Windows-job over en bevat een release enkel de Mac-bestanden.

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
