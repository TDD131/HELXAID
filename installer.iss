; HELXAID Installer Script
; Created for Inno Setup 6.x

#define MyAppName "HELXAID"
#define MyAppVersion "4.8"
#define MyAppPublisher "TDD"
#define MyAppExeName "HELXAID.exe"

[Setup]
; Unique identifier for this application
AppId={{B8F42D1C-3E5A-4F9C-8D2B-1A7E6C9F0D3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Output installer settings
OutputDir=dist
OutputBaseFilename=HELXAID Setup
; Compression
Compression=lzma2
SolidCompression=yes
; Appearance
WizardStyle=modern
; Icon for installer
SetupIconFile=python\UI Icons\launcher-icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Require Windows 10+
MinVersion=10.0
; Require admin so it installs to C:\Program Files
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Let user choose to add to startup
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start automatically with Windows (shows in Task Manager)"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Main executable (built by PyInstaller)
Source: "dist\HELXAID.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; Startup shortcut (optional) - This is what shows in Task Manager's Startup Apps!
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
; Option to run after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
