; Inno Setup (gratis). Bouwen: ISCC /DAppVersion=1.2.3 installer\huurklaar-meldingen.iss  (doet scripts\build-windows.ps1).
; Installeert in de map van de gebruiker (%LOCALAPPDATA%\Programs): geen beheerdersrechten, geen UAC-prompt.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Huurklaar Meldingen"
#define AppExe "Huurklaar Meldingen.exe"

[Setup]
; Het AppId moet voor altijd gelijk blijven: zo herkent een nieuwe versie de oude en werkt ze die bij.
AppId={{6F1B3C52-8D0A-4C57-9E4B-2A7D91C3B8E6}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Huurklaar
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Huurklaar-Meldingen-Setup-{#AppVersion}
SetupIconFile=..\assets\AppIcon.ico
UninstallDisplayIcon={app}\{#AppExe}
VersionInfoVersion={#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Dezelfde naam als platform/windows_single.py: installer en uninstaller waarschuwen als de app nog draait.
AppMutex=HuurklaarMeldingenSingleInstance

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
dutch.Autostart=Huurklaar Meldingen starten bij het aanmelden bij Windows
french.Autostart=Lancer Huurklaar Meldingen à l'ouverture de session Windows
english.Autostart=Start Huurklaar Meldingen when I sign in to Windows
dutch.LaunchNow=Huurklaar Meldingen nu starten
french.LaunchNow=Lancer Huurklaar Meldingen maintenant
english.LaunchNow=Start Huurklaar Meldingen now

[Tasks]
Name: "autostart"; Description: "{cm:Autostart}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Registry]
; Dezelfde waarde als de app zelf schrijft (RUN_VALUE in platform/windows_registry.py); weg bij het verwijderen.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "HuurklaarMeldingen"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Wist de bewaarde sleutel (Credential Manager) en 'start bij aanmelden'.
Filename: "{app}\{#AppExe}"; Parameters: "--forget"; RunOnceId: "Forget"; Flags: runhidden
