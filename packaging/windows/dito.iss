; Instalador do Dito para Windows: app Flutter nativo C++ (sem Python).
;
;   ISCC.exe /DMyAppVersion=1.2.0 packaging\windows\dito.iss
;
; Instala em %LOCALAPPDATA%\Programs\Dito, sem pedir UAC.

#ifndef MyAppVersion
  #define MyAppVersion "1.2.7"
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
Name: "model_small"; Description: "Baixar o modelo de voz padrão agora (small - ~484 MB, recomendado)"; GroupDescription: "Modelos de transcrição:"
Name: "model_tiny"; Description: "Baixar o modelo Mínimo (tiny - ~75 MB)"; GroupDescription: "Modelos adicionais:"; Flags: unchecked
Name: "model_base"; Description: "Baixar o modelo Básico (base - ~145 MB)"; GroupDescription: "Modelos adicionais:"; Flags: unchecked
Name: "model_medium"; Description: "Baixar o modelo Bom (medium - ~1,5 GB)"; GroupDescription: "Modelos adicionais:"; Flags: unchecked
Name: "model_large"; Description: "Baixar o modelo Melhor (large-v3 - ~3,1 GB)"; GroupDescription: "Modelos adicionais:"; Flags: unchecked

[InstallDelete]
; Limpeza do motor Python legado e DLLs antigas
Type: filesandordirs; Name: "{app}\dito-engine"
Type: files; Name: "{app}\hotkey_manager_windows_plugin.dll"
Type: files; Name: "{app}\local_notifier_plugin.dll"
Type: files; Name: "{app}\system_tray_plugin.dll"
Type: files; Name: "{app}\tray_manager_plugin.dll"

[Files]
Source: "{#AppBundle}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "download_model.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"; Tasks: desktopicon
; Parameters --startup: no boot o app sobe em segundo plano (bandeja), sem abrir a janela.
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--startup"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"; Tasks: startup

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File ""{app}\download_model.ps1"" -Model small"; StatusMsg: "Baixando o modelo de voz padrão Small (~484 MB)..."; Flags: waituntilterminated runhidden; Tasks: model_small
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File ""{app}\download_model.ps1"" -Model tiny"; StatusMsg: "Baixando o modelo Mínimo Tiny (~75 MB)..."; Flags: waituntilterminated runhidden; Tasks: model_tiny
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File ""{app}\download_model.ps1"" -Model base"; StatusMsg: "Baixando o modelo Básico Base (~145 MB)..."; Flags: waituntilterminated runhidden; Tasks: model_base
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File ""{app}\download_model.ps1"" -Model medium"; StatusMsg: "Baixando o modelo Bom Medium (~1,5 GB)..."; Flags: waituntilterminated runhidden; Tasks: model_medium
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File ""{app}\download_model.ps1"" -Model large-v3"; StatusMsg: "Baixando o modelo Melhor Large-v3 (~3,1 GB)..."; Flags: waituntilterminated runhidden; Tasks: model_large
Filename: "{app}\{#MyAppExe}"; Description: "Abrir o Dito"; Flags: nowait postinstall skipifsilent

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
           'Suas gravações continuam em Documentos\Dito e as configurações em ' +
           '%APPDATA%\dito.',
           mbInformation, MB_OK);
  end;
end;
