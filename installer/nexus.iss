; Inno Setup 6 script for NEXUS.  Build with:  ISCC.exe /DAppVersion=0.5.0 installer\nexus.iss
; (scripts\build.ps1 does this for you.)  Run it AFTER dist\NEXUS exists.
;
; Design rules
;  * Per-user install by default: no administrator rights, nothing outside the user profile.
;  * The install folder holds only program files. Conversations, reminders, settings and logs
;    live in %LOCALAPPDATA%\NEXUS and are NOT removed by upgrades; the uninstaller asks first.
;  * The installer never changes Windows startup. That is a setting inside NEXUS the user turns on.
;  * Natural voice (Kokoro) is an optional, unchecked step because it is a large download (roughly 1-2 GB).

#ifndef AppVersion
  #define AppVersion "0.5.0"
#endif

[Setup]
; Never change this GUID: it is how upgrades recognise an existing NEXUS install.
AppId={{DDC19DBF-62E1-46B4-9CD8-DD892FFA11FC}
AppName=NEXUS
AppVersion={#AppVersion}
AppVerName=NEXUS {#AppVersion}
AppPublisher=NEXUS
AppPublisherURL=https://github.com/12nshuti-cpu/1nexus
AppSupportURL=https://github.com/12nshuti-cpu/1nexus/issues
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\NEXUS
DisableProgramGroupPage=yes
DefaultGroupName=NEXUS
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\installer_output
OutputBaseFilename=NEXUS-Setup-{#AppVersion}
SetupIconFile=..\assets\nexus.ico
UninstallDisplayIcon={app}\NEXUS.exe
UninstallDisplayName=NEXUS
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Matches the single-instance mutex created in app.py, so setup/uninstall notice a running NEXUS.
AppMutex=NEXUS_SINGLE_INSTANCE_2026
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\NEXUS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NEXUS"; Filename: "{app}\NEXUS.exe"
Name: "{autoprograms}\NEXUS - install natural voice (Kokoro)"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\setup_kokoro.ps1"""; IconFilename: "{app}\NEXUS.exe"; Comment: "Optional: large download (roughly 1-2 GB). Needs Python 3.10-3.12."
Name: "{autodesktop}\NEXUS"; Filename: "{app}\NEXUS.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NEXUS.exe"; Description: "Launch NEXUS"; Flags: nowait postinstall skipifsilent
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\setup_kokoro.ps1"""; Description: "Install natural voice (Kokoro) now - large download (roughly 1-2 GB), needs Python 3.10-3.12"; Flags: postinstall skipifsilent unchecked

[Code]
procedure StopHelper();
var
  ResultCode: Integer;
begin
  // The optional Ctrl+Alt+N helper would keep its .exe locked during upgrade/uninstall.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM NEXUSHotkey.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopHelper();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
    StopHelper();
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\NEXUS');
    if (not UninstallSilent) and DirExists(DataDir) then
      if MsgBox('Also delete your NEXUS data (conversations, memories, reminders, settings, logs and the Kokoro voice environment)?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Choose No to keep it for a future reinstall. Saved API keys are stored in Windows Credential Manager (entry "NEXUS") and are not removed here.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
