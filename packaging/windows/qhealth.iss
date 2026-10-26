; Inno Setup script for the QHealth Windows installer.
; Build after PyInstaller (from the repository root):
;   iscc /DAppVersion=3.0.0 packaging\windows\qhealth.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C2F7D1E-6B4A-4E1F-9D3C-2A7B5E9F4C11}
AppName=QHealth
AppVersion={#AppVersion}
AppVerName=QHealth {#AppVersion}
AppPublisher=Qssaf
AppPublisherURL=https://github.com/Qssaf/qhealth
AppSupportURL=https://github.com/Qssaf/qhealth/issues
; Per-user install by default (no admin prompt); "Install for all users" stays available
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
DefaultDirName={autopf}\QHealth
DefaultGroupName=QHealth
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=QHealth-{#AppVersion}-Setup
SetupIconFile=qhealth.ico
UninstallDisplayIcon={app}\QHealth.exe
UninstallDisplayName=QHealth
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Upgrades: close a running QHealth first so its files can be replaced
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "autostart"; Description: "Start QHealth when I sign in (keeps tracking running in the tray)"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\QHealth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\QHealth"; Filename: "{app}\QHealth.exe"; AppUserModelID: "Qssaf.QHealth"
Name: "{autodesktop}\QHealth"; Filename: "{app}\QHealth.exe"; AppUserModelID: "Qssaf.QHealth"; Tasks: desktopicon

[Registry]
; Same value the tray's "Start with Windows" toggle manages
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "QHealth"; \
    ValueData: """{app}\QHealth.exe"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\QHealth.exe"; Description: "{cm:LaunchProgram,QHealth}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM QHealth.exe"; Flags: runhidden; RunOnceId: "StopQHealth"
; Activity history in %LOCALAPPDATA%\QHealth is kept on purpose
