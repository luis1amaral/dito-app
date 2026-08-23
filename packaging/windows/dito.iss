; Instalador do Dito para Windows: app Flutter nativo C++ (sem Python).
;
;   ISCC.exe /DMyAppVersion=1.2.0 packaging\windows\dito.iss
;
; Instala em %LOCALAPPDATA%\Programs\Dito, sem pedir UAC.

#ifndef MyAppVersion
  #define MyAppVersion "1.2.9"
#endif
#define MyAppName "Dito"
#define MyAppExe "dito_app.exe"

; O build/ é montado por construir.ps1 com os binários C++ nativos.
#define AppBundle "..\..\build\windows\x64\runner\Release"
#define IconFile "..\..\assets\icons\dito.ico"

[Setup]
AppId={{8E3B5A2C-4D71-4C0E-9A6F-2F1D6B0A7E31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Luis Amaral
AppPublisherURL=https://github.com/luis1amaral/dito-app
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\build\windows\installer
OutputBaseFilename=dito-{#MyAppVersion}-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "startup"; Description: "Iniciar o Dito junto com o Windows (fica só na bandeja)"; GroupDescription: "Ao ligar o computador:"
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[InstallDelete]
; Limpeza do motor Python legado e DLLs antigas
Type: filesandordirs; Name: "{app}\dito-engine"
Type: files; Name: "{app}\hotkey_manager_windows_plugin.dll"
Type: files; Name: "{app}\local_notifier_plugin.dll"
Type: files; Name: "{app}\system_tray_plugin.dll"
Type: files; Name: "{app}\tray_manager_plugin.dll"
; Sobra da arquitetura multi-janela: o Inno nao apaga arquivo que saiu do pacote.
Type: files; Name: "{app}\desktop_multi_window_plugin.dll"

[Files]
Source: "{#AppBundle}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Todo atalho sobe na bandeja: a janela so abre pelo menu do icone, nunca sozinha.
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--startup"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--startup"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"; Tasks: desktopicon
; Parameters --startup: no boot o app sobe em segundo plano (bandeja), sem abrir a janela.
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--startup"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"; Tasks: startup

[Run]
; --startup: termina a instalacao com o app pronto na bandeja, sem abrir janela nenhuma.
Filename: "{app}\{#MyAppExe}"; Parameters: "--startup"; Description: "Deixar o Dito pronto na bandeja"; Flags: nowait postinstall skipifsilent

[Code]
// O Windows guarda o icone antigo em cache e continua mostrando o do instalador anterior.
procedure SHChangeNotify(wEventId: Integer; uFlags: Cardinal; dwItem1, dwItem2: Cardinal);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure StopApp();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'),
       '/F /IM {#MyAppExe}', '',
       SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // SHCNE_ASSOCCHANGED: manda o shell reler os icones em vez de servir o do cache.
  if CurStep = ssPostInstall then SHChangeNotify($08000000, 0, 0, 0);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopApp();

  if CurUninstallStep = usPostUninstall then
  begin
    // As gravações e a configuração são do dono: essas nunca apagamos.
    MsgBox('O Dito foi removido com sucesso.' + #13#10 + #13#10 +
           'Suas gravações continuam na pasta Dito do seu usuário e as configurações em ' +
           '%APPDATA%\dito.',
           mbInformation, MB_OK);
  end;
end;
