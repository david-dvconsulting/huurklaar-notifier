# Bouwt op Windows: Huurklaar-Meldingen.exe (één bestand), de map voor de installer en Huurklaar-Meldingen-Setup-<versie>.exe.
# Elke stap faalt hard; de self-test draait vóór het bouwen én in de gebouwde .exe, met een time-out.
# Gebruik (PowerShell, vanuit de repo):  scripts\build-windows.ps1 [-Version 1.2.3] [-SkipInstaller]
# Vereist: Python 3.13 en (voor de installer) Inno Setup 6, https://jrsoftware.org/isinfo.php (gratis).
param(
  [string]$Version = "",
  [switch]$SkipInstaller,
  [int]$SelftestSeconds = 120
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Run([string]$what, [scriptblock]$cmd) {
  Write-Host "==> $what"
  & $cmd
  if ($LASTEXITCODE -ne 0) { throw "$what mislukt (exitcode $LASTEXITCODE)" }
}

# Self-test van een gebouwde .exe. Een --noconsole-programma keert direct terug, dus we wachten op het proces;
# een melding die blijft hangen geeft zo een rode run in plaats van een eeuwige wachttijd.
function Selftest-Exe([string]$exe) {
  $out = Join-Path $env:TEMP "huurklaar-selftest-$([guid]::NewGuid().ToString('N')).txt"
  $p = Start-Process -FilePath $exe -ArgumentList @("--selftest", "--selftest-output", $out) -PassThru
  if (-not $p.WaitForExit($SelftestSeconds * 1000)) {
    $p.Kill()
    throw "self-test in $exe duurde langer dan $SelftestSeconds seconden (hangt)"
  }
  if (Test-Path $out) { Get-Content $out | Write-Host }
  if ($p.ExitCode -ne 0) { throw "self-test in $exe mislukt (exitcode $($p.ExitCode))" }
}

if (-not $Version) { $Version = (python -m huurklaar_notifier --version).Trim() }
$Version = $Version.TrimStart("v")

Run "afhankelijkheden installeren" { python -m pip install -e ".[windows,dev]" --quiet }
Run "self-test (Python)" { python -m huurklaar_notifier --selftest }
Run "icoon maken" { python scripts/make-icons-windows.py }
Run "versiebestand maken" { python scripts/make-version-file.py $Version build/version.txt }

Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
# Absolute paden: PyInstaller leest relatieve paden vanaf --specpath (build\), niet vanaf de repo.
$root = (Get-Location).Path
$common = @(
  "--noconfirm", "--noconsole", "--noupx", "--specpath", "build",
  "--icon", "$root\assets\AppIcon.ico", "--version-file", "$root\build\version.txt",
  "--add-data", "$root\assets\AppIcon.ico;assets", "--paths", "$root\src",
  "--hidden-import", "pystray._win32", "--collect-submodules", "winrt",
  "--collect-submodules", "keyring.backends", "--collect-submodules", "win32ctypes"
)
# Zonder UPX en met versiegegevens: minder kans op een valse virusmelding.
Run "bouwen: één .exe" {
  python -m PyInstaller @common --onefile --name "Huurklaar-Meldingen" --workpath build/onefile "$root\scripts\entry.py"
}
Selftest-Exe (Resolve-Path "dist/Huurklaar-Meldingen.exe")

# De installer gebruikt een map (onedir): start sneller (niets uitpakken naar %TEMP% bij elke start) en
# loopt minder tegen virusscanners aan dan een zelfuitpakkend bestand.
Run "bouwen: map voor de installer" {
  python -m PyInstaller @common --onedir --name "Huurklaar Meldingen" --workpath build/onedir "$root\scripts\entry.py"
}
Selftest-Exe (Resolve-Path "dist/Huurklaar Meldingen/Huurklaar Meldingen.exe")

if ($SkipInstaller) { Write-Host "Klaar (zonder installer): dist\Huurklaar-Meldingen.exe"; exit 0 }
$iscc = @(
  (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 niet gevonden. Installeer het (gratis) of gebruik -SkipInstaller." }
# Een voorlooptekst zoals 0.0.1-rc.1 mag niet in VersionInfoVersion: neem de eerste vier getallen.
$parts = @([regex]::Matches(($Version -split "-")[0], "\d+") | ForEach-Object { $_.Value })
while ($parts.Count -lt 4) { $parts += "0" }
$numeric = ($parts | Select-Object -First 4) -join "."
Run "installer maken (Inno Setup)" { & $iscc "/DAppVersion=$Version" "/DAppVersionNumeric=$numeric" "installer\huurklaar-meldingen.iss" }
Write-Host "Klaar: dist\Huurklaar-Meldingen.exe en dist\Huurklaar-Meldingen-Setup-$Version.exe"
