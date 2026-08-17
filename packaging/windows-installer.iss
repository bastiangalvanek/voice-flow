; Inno-Setup-Bauplan fuer Voice Flow (Windows).
; Erzeugt ein normales Installationsprogramm mit Fenster, Startmenue-Eintrag,
; optionaler Desktop-Verknuepfung und Deinstallation.
;
; Gebaut wird es im GitHub-Workflow:  ISCC packaging\windows-installer.iss
; Version kommt von aussen:           ISCC /DMyVersion=0.3.1 ...

#ifndef MyVersion
  #define MyVersion "0.3.0"
#endif

#define MyAppName "Voice Flow"
#define MyAppPublisher "Bastian Galvanek"
#define MyAppExeName "VoiceFlow.exe"

[Setup]
AppId={{7C4C4F1E-52D2-4C0E-9A8E-0E5F2E7B9A11}
AppName={#MyAppName}
AppVersion={#MyVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/bastiangalvanek/voice-flow
DefaultDirName={autopf}\Voice Flow
DefaultGroupName=Voice Flow
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=VoiceFlow-{#MyVersion}-Setup
SetupIconFile=..\src\voice_flow\assets\voice-flow.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
; Deutsch, weil die App deutsch ist.
ShowLanguageDialog=no

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknuepfung auf dem Desktop anlegen"; GroupDescription: "Zusaetzliche Verknuepfungen:"
Name: "autostart"; Description: "Voice Flow beim Anmelden starten"; GroupDescription: "Start:"; Flags: unchecked

[Files]
; Alles, was PyInstaller unter dist\VoiceFlow abgelegt hat (Programm, Qt, Logo,
; die Modus-Zeichen Clawd und Chrome).
Source: "..\dist\VoiceFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Voice Flow"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Voice Flow deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Voice Flow"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\Voice Flow"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Voice Flow jetzt starten"; Flags: nowait postinstall skipifsilent

[Messages]
deutsch.WelcomeLabel2=Damit installierst du [name/ver].%n%nDanach brauchst du noch einen OpenAI-Schluessel: lege die Datei %USERPROFILE%\.voice-flow\.env an mit der Zeile OPENAI_API_KEY=sk-...%n%nTasten: F8 Aufnahme, F7 Screenshot, F6 markieren.%n%ndeveloped with Herz by Bastian Galvanek
