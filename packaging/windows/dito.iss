; O instalador de distribuição do Dito, para máquina SEM Python.
;
;   packaging\windows\construir.ps1        monta o bundle e compila isto
;   ISCC.exe /DMyAppVersion=0.3.10 packaging\windows\dito.iss
;
; Instala em %LOCALAPPDATA%\Programs\Dito, sem UAC: é a máquina do dono e elevar não compra nada.
; O desinstalador NÃO apaga %LOCALAPPDATA%\dito\state nem Documents\Dito — é onde moram as
; gravações, igual ao postrm do .deb no Linux. tests/test_packaging.py prende essa promessa.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "Dito"
#define MyAppId "com.defalt.dito"
#define BundleDir "..\..\build\windows\dist\Dito"
#define IconFile "..\..\src\dito\ui\assets\dito.ico"

[Setup]
AppId={{8E3B5A2C-4D71-4C0E-9A6F-2F1D6B0A7E31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Luis Amaral
AppPublisherURL=https://github.com/luis1amaral/dito
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Sem UAC: {autopf} vira %LOCALAPPDATA%\Programs, que o usuário escreve sem elevar.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\build\windows\installer
OutputBaseFilename=dito-{#MyAppVersion}-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\ditow.exe
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
; Nós mesmos encerramos o Dito em PrepareToInstall; o Restart Manager só traria uma janela a mais.
CloseApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
; MARCADO por padrão de propósito: quem instala este .exe é o dono da máquina, e um login tem
; que chegar já ditando. O instalador por script (instalar.ps1) faz o contrário, e explica lá.
Name: "startup"; Description: "Iniciar o Dito junto com o Windows"; GroupDescription: "Ao ligar o computador:"
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "addtopath"; Description: "Deixar o comando ""dito"" disponível no terminal"; GroupDescription: "Atalhos:"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID é o equivalente em Pascal do packaging\windows\set_app_id.py: sem ele a
; notificação do Windows sai com o nome do interpretador ("Python") em vez de "Dito".
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\ditow.exe"; Parameters: "ui"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "{#MyAppId}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\ditow.exe"; Parameters: "ui"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "{#MyAppId}"; Tasks: desktopicon
; `listen` e não `ui`: no login só pode aparecer o ícone da bandeja, nunca uma janela.
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\ditow.exe"; Parameters: "listen"; Comment: "Dito - ditado por voz"; AppUserModelID: "{#MyAppId}"; Tasks: startup

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Flags: preservestringtype; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\ditow.exe"; Parameters: "listen"; Description: "Começar a ditar agora"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopDito();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM dito.exe /IM ditow.exe', '',
       SW_HIDE, ewWaitUntilTerminated, Code);
end;

function NeedsAddPath(Dir: string): Boolean;
var
  Path: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';') = 0;
end;

procedure RemoveFromPath(Dir: string);
var
  Path: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path) then exit;
  Path := ';' + Path + ';';
  StringChangeEx(Path, ';' + Dir + ';', ';', True);
  Path := Copy(Path, 2, Length(Path) - 2);
  RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopDito();
  Result := '';
end;

procedure CurUninstallStepChanged(CurStep: TUninstallStep);
begin
  if CurStep = usUninstall then
  begin
    StopDito();
    RemoveFromPath(ExpandConstant('{app}'));
  end;
  // As gravações e a biblioteca ficam. Apagá-las seria a única perda irreversível deste programa.
  if (CurStep = usPostUninstall) and (not UninstallSilent) then
    MsgBox('O Dito foi removido.' + #13#10#13#10 +
           'As suas gravações NÃO foram apagadas:' + #13#10 +
           ExpandConstant('{localappdata}\dito\state') + #13#10 +
           ExpandConstant('{userdocs}\Dito'),
           mbInformation, MB_OK);
end;
