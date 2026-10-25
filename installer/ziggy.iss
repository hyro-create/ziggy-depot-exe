; Script Inno Setup 6.3 ou plus récent  —  génère installer_output\Ziggy-Setup.exe
; Compilation : installer.bat  (ou : ISCC.exe /DMyAppVersion=1.0.0 installer\ziggy.iss)
; Principes : installation PAR UTILISATEUR (aucun droit administrateur), données personnelles dans
; %LOCALAPPDATA%\Ziggy JAMAIS touchées par l'installation, la mise à jour ou (sans accord) la désinstallation.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "Ziggy"
#define MyAppExeName "Ziggy.exe"
#define MyAppPublisher "Solar"
#define MyAppGuid "B7C2E1A4-5D3F-4E8A-9C61-2F0A7D4E9B15"

[Setup]
AppId={{#MyAppGuid}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=Installateur de Ziggy
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer_output
OutputBaseFilename=Ziggy-Setup
SetupIconFile=..\assets\ziggy.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=ZiggyAppMutex
CloseApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Uniquement le PROGRAMME. Aucune donnée personnelle n'est livrée ni écrasée.
Source: "..\dist\Ziggy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Mise à jour propre : on retire les anciennes bibliothèques du PROGRAMME avant de copier les nouvelles.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppGuid}_is1';
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

function VersionPart(S: String; Index: Integer): Integer;
var
  I, P: Integer;
  T: String;
begin
  Result := 0;
  T := S;
  for I := 0 to Index do
  begin
    P := Pos('.', T);
    if I < Index then
    begin
      if P = 0 then Exit;
      Delete(T, 1, P);
    end
    else
    begin
      if P > 0 then T := Copy(T, 1, P - 1);
      Result := StrToIntDef(T, 0);
    end;
  end;
end;

function CompareVersions(A, B: String): Integer;
var
  I, X, Y: Integer;
begin
  Result := 0;
  for I := 0 to 3 do
  begin
    X := VersionPart(A, I);
    Y := VersionPart(B, I);
    if X < Y then begin Result := -1; Exit; end;
    if X > Y then begin Result := 1; Exit; end;
  end;
end;

function InstalledVersion(): String;
var
  V: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', V) then
    Result := V
  else if RegQueryStringValue(HKLM, UninstallKey, 'DisplayVersion', V) then
    Result := V;
end;

function InitializeSetup(): Boolean;
var
  Old: String;
begin
  Result := True;
  Old := InstalledVersion();
  if (Old <> '') and (CompareVersions(Old, '{#MyAppVersion}') > 0) then
    Result := MsgBox('Une version plus récente de Ziggy (' + Old + ') est déjà installée.' + #13#10 +
                     'Voulez-vous vraiment installer la version plus ancienne ({#MyAppVersion}) ?' + #13#10#13#10 +
                     'Vos données personnelles seront conservées.',
                     mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

procedure InitializeWizard();
var
  Old: String;
begin
  Old := InstalledVersion();
  if Old <> '' then
  begin
    if CompareVersions(Old, '{#MyAppVersion}') < 0 then
      WizardForm.WelcomeLabel2.Caption := 'Ziggy ' + Old + ' est installé. Cet assistant va le mettre à jour vers la version {#MyAppVersion}.' +
        #13#10#13#10 + 'Vos données personnelles (mémoire, historique, paramètres, clé API) sont conservées : rien n''est à réinstaller ni à ressaisir.'
    else
      WizardForm.WelcomeLabel2.Caption := 'Ziggy ' + Old + ' est déjà installé. Cet assistant va le réinstaller.' +
        #13#10#13#10 + 'Vos données personnelles (mémoire, historique, paramètres, clé API) sont conservées.';
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  RC: Integer;
begin
  Result := '';
  if CheckForMutexes('ZiggyAppMutex') then
  begin
    if MsgBox('Ziggy est en cours d''exécution et doit être fermé pour continuer.' + #13#10 +
              'Fermer Ziggy maintenant ? (vos données sont enregistrées automatiquement)',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#MyAppExeName} /F', '', SW_HIDE, ewWaitUntilTerminated, RC);
      Sleep(1500);
      if CheckForMutexes('ZiggyAppMutex') then
        Result := 'Ziggy est toujours ouvert. Quittez-le (icône de la barre des tâches, puis Quitter) et relancez l''installation.';
    end
    else
      Result := 'Fermez Ziggy puis relancez l''installation.';
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKCU, RunKey, 'Ziggy');
    DataDir := ExpandConstant('{localappdata}\Ziggy');
    if DirExists(DataDir) and (not UninstallSilent) then
    begin
      if MsgBox('Ziggy est désinstallé.' + #13#10#13#10 +
                'Voulez-vous aussi supprimer vos données personnelles (mémoire, historique, paramètres, clé API) ?' + #13#10 +
                DataDir + #13#10#13#10 +
                'Si vous répondez Non, elles sont conservées et retrouvées si vous réinstallez Ziggy.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
