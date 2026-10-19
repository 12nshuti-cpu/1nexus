; NEXUS Inno Setup - minimal
[Setup]
AppName=NEXUS
AppVersion=0.6.0
AppPublisher=NEXUS
DefaultDirName={pf}\NEXUS
DefaultGroupName=NEXUS
OutputBaseFilename=NEXUS-Setup-0.6.0
OutputDir=..\dist
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\NEXUS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\NEXUS"; Filename: "{app}\NEXUS.exe"
Name: "{userdesktop}\NEXUS"; Filename: "{app}\NEXUS.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\NEXUS.exe"; Description: "Launch NEXUS"; Flags: nowait postinstall skipifsilent
