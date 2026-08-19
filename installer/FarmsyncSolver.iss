; The installer a non-technical user double-clicks (spec 11.3).
;
;     iscc /DAppVersion=1.2.0 /DAppNumericVersion=1.2.0 installer\FarmsyncSolver.iss
;
; It wraps the packed folder in dist\FarmsyncSolver and writes
; dist\FarmsyncSolver-Setup-<version>.exe. Only the release workflow runs it.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#ifndef AppNumericVersion
  #define AppNumericVersion "0.0.0"
#endif

#define AppName "FarmsyncSolver"
#define AppExeName "FarmsyncSolver.exe"
; Both are relative to this file.
#define PackedFolder "..\dist\FarmsyncSolver"
#define OutputFolder "..\dist"

[Setup]
; Never change AppId: it is how Windows knows an update from a second product.
AppId={{4C1D9A0E-2E6B-4C7B-9F3E-6B2A5F8D71C4}
AppName={#AppName}
AppVersion={#AppVersion}
VersionInfoVersion={#AppNumericVersion}
AppPublisher={#AppName}
WizardStyle=modern

; Per-user: no admin, no UAC — not here, and not on every silent auto-update.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes

; The mutex the app takes at startup. Setup refuses to run while the app is open.
; The updater exits the app first, which drops the mutex, so a silent update is
; not blocked by it (spec 12).
AppMutex=FarmsyncSolverSingleInstance
CloseApplications=yes
RestartApplications=yes

ArchitecturesAllowed=x64compatible
OutputDir={#OutputFolder}
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=..\assets\{#AppName}.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes

[Languages]
; Named so the {cm:...} message ids below always resolve.
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: checkedonce

[Files]
Source: "{#PackedFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; ~2 MB, run only when the runtime is missing. A missing WebView2 Runtime is a
; blank white window with no error, which the app itself cannot report.
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; The bundled file is a ~2 MB bootstrapper: it pulls about 200 MB from Microsoft
; before it installs anything. That wait is minutes long on a slow line, so the
; step says what it is doing and the bar keeps moving (issue #32).
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
  StatusMsg: "Downloading and installing the Microsoft Edge WebView2 Runtime (about 200 MB). This can take a few minutes..."; \
  Check: not WebView2Installed; Flags: waituntilterminated; \
  BeforeInstall: MarqueeOn; AfterInstall: MarqueeOff
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent

[Code]
const
  { The WebView2 Runtime's own product code under EdgeUpdate. }
  WebView2Client = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function VersionPresent(Root: Integer; Key: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2Installed: Boolean;
begin
  { Per-machine, in both registry views — Setup is 32-bit, so plain HKLM is the
    redirected one and HKLM64 is needed for the native view — or per-user.
    Any one of them is enough. }
  Result :=
    VersionPresent(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2Client) or
    VersionPresent(HKLM64, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2Client) or
    VersionPresent(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2Client);
end;

procedure MarqueeOn;
begin
  { waituntilterminated blocks this thread, so no percentage can be counted.
    A marquee at least shows the installer is alive. }
  WizardForm.ProgressGauge.Style := npbstMarquee;
end;

procedure MarqueeOff;
begin
  WizardForm.ProgressGauge.Style := npbstNormal;
end;

procedure AddMemo(var Memo: String; Part, NewLine: String);
begin
  { Every part Inno hands us, in Inno's own order. Naming them one by one would
    quietly drop the day a [Components] or [Types] section is added. }
  if Part = '' then
    Exit;
  if Memo <> '' then
    Memo := Memo + NewLine + NewLine;
  Memo := Memo + Part;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := '';
  AddMemo(Result, MemoUserInfoInfo, NewLine);
  AddMemo(Result, MemoDirInfo, NewLine);
  AddMemo(Result, MemoTypeInfo, NewLine);
  AddMemo(Result, MemoComponentsInfo, NewLine);
  AddMemo(Result, MemoGroupInfo, NewLine);
  AddMemo(Result, MemoTasksInfo, NewLine);

  { Said before Install is pressed, not after the window has already gone still. }
  if not WebView2Installed then
    Result := Result + NewLine + NewLine +
      'Microsoft Edge WebView2 Runtime:' + NewLine +
      Space + 'This PC does not have it, so Setup will download it from' + NewLine +
      Space + 'Microsoft (about 200 MB). This can take a few minutes on' + NewLine +
      Space + 'a slow connection.' + NewLine;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserData: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  UserData := ExpandConstant('{userappdata}\{#AppName}');
  if not DirExists(UserData) then
    Exit;

  { One question, asked once, covering keys and logs together. Default No, and a
    silent uninstall takes that default, so an auto-update never eats the keys. }
  if SuppressibleMsgBox(
       'Also delete your saved keys and logs?' + #13#10#13#10 +
       'Choose No to keep them for when you install ' + '{#AppName}' + ' again.',
       mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    DelTree(UserData, True, True, True);
end;
