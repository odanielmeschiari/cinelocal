; Inno Setup script (https://jrsoftware.org/isinfo.php): builds dist\CineLocal-windows-x86_64-setup.exe from the
; PyInstaller folder dist\CineLocal.   iscc /DAppVersion=1.12.0 installer\cinelocal.iss
; Per-user install (no administrator rights). The uninstaller (Settings > Apps) asks whether to also delete the data.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId=cinelocal
AppName=CineLocal
AppVersion={#AppVersion}
AppPublisher=CineLocal
DefaultDirName={autopf}\CineLocal
DefaultGroupName=CineLocal
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\cinelocal.ico
UninstallDisplayIcon={app}\CineLocal.exe
OutputDir=..\dist
OutputBaseFilename=CineLocal-windows-x86_64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[InstallDelete]
; leftovers of the old install.bat (Python + venv) in the same folder
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\cinelocal"
Type: filesandordirs; Name: "{app}\assets"

[Files]
Source: "..\dist\CineLocal\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\CineLocal"; Filename: "{app}\CineLocal.exe"
Name: "{autodesktop}\CineLocal"; Filename: "{app}\CineLocal.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CineLocal.exe"; Description: "Open CineLocal"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox('Also delete your library, posters and settings?' + #13#10 +
              'Your movies are never deleted. This cannot be undone.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\cinelocal'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\cinelocal'), True, True, True);
    end;
end;
