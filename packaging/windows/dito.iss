; Instalador do Dito para Windows: app Flutter + motor de transcrição.
;
;   ISCC.exe /DMyAppVersion=1.0.0 packaging\windows\dito.iss
;
; Instala em %LOCALAPPDATA%\Programs\Dito, sem pedir UAC.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "Dito"
#define MyAppExe "dito_app.exe"

; O build/ é montado por construir.ps1 e já traz o motor dentro.
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
Name: "model"; Description: "Baixar agora todos os modelos de voz (cerca de 5,3 GB)"; GroupDescription: "Modelos de transcrição:%nCom todos baixados, trocar de modelo nos Ajustes funciona na hora. Se não baixar agora, o Dito baixa sozinho o que faltar."
Name: "gpu"; Description: "Baixar a aceleração por placa de vídeo NVIDIA (1,3 GB)"; GroupDescription: "Placa de vídeo:%nSó marque se esta máquina tem placa NVIDIA - a transcrição fica cerca de 3x mais rápida."; Flags: unchecked

[InstallDelete]
; Plugins removidos na 1.1.3: instalação antiga deixa a DLL órfã para trás.
Type: files; Name: "{app}\hotkey_manager_windows_plugin.dll"
Type: files; Name: "{app}\local_notifier_plugin.dll"
Type: files; Name: "{app}\system_tray_plugin.dll"
Type: files; Name: "{app}\tray_manager_plugin.dll"

[Files]
; Um Source só: o motor já vem dentro do bundle, montado por construir.ps1.
Source: "{#AppBundle}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"; Tasks: desktopicon
; Parameters --startup: no boot o app sobe em segundo plano (bandeja), sem abrir a janela.
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--startup"; Comment: "Dito - ditado por voz offline"; AppUserModelID: "com.defalt.dito"; Tasks: startup

[Run]
; Um por modelo, para o assistente mostrar de qual ele esta cuidando. runhidden: o motor e um
; programa de console, e sem isso pisca uma janela preta na cara de quem instala.
Filename: "{app}\dito-engine\dito-engine.exe"; Parameters: "download-model tiny"; StatusMsg: "Baixando o modelo Mínimo (1 de 5, ~75 MB)..."; Flags: waituntilterminated runhidden; Tasks: model
Filename: "{app}\dito-engine\dito-engine.exe"; Parameters: "download-model base"; StatusMsg: "Baixando o modelo Básico (2 de 5, ~145 MB)..."; Flags: waituntilterminated runhidden; Tasks: model
Filename: "{app}\dito-engine\dito-engine.exe"; Parameters: "download-model small"; StatusMsg: "Baixando o modelo Equilibrado (3 de 5, ~484 MB)..."; Flags: waituntilterminated runhidden; Tasks: model
Filename: "{app}\dito-engine\dito-engine.exe"; Parameters: "download-model medium"; StatusMsg: "Baixando o modelo Bom (4 de 5, ~1,5 GB)..."; Flags: waituntilterminated runhidden; Tasks: model
Filename: "{app}\dito-engine\dito-engine.exe"; Parameters: "download-model large-v3"; StatusMsg: "Baixando o modelo Melhor (5 de 5, ~3,1 GB)..."; Flags: waituntilterminated runhidden; Tasks: model
Filename: "{app}\dito-engine\dito-engine.exe"; Parameters: "gpu --install"; StatusMsg: "Baixando a aceleração por placa de vídeo (~1,3 GB, pode demorar)..."; Flags: waituntilterminated runhidden; Tasks: gpu
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
       '/F /IM {#MyAppExe} /IM dito-engine.exe', '',
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
var
  Cuda: String;
begin
  if CurUninstallStep = usUninstall then
    StopApp();

  if CurUninstallStep = usPostUninstall then
  begin
    // A aceleração pesa 1,9 GB e não serve para mais nada sem o app.
    Cuda := ExpandConstant('{localappdata}\dito\cuda');
    if DirExists(Cuda) then
      DelTree(Cuda, True, True, True);

    // As gravações e a configuração são do dono: essas nunca apagamos.
    MsgBox('O Dito foi removido, junto com a aceleração de vídeo.' + #13#10 + #13#10 +
           'Suas gravações continuam em Documentos\Dito e as configurações em ' +
           '%APPDATA%\dito.',
           mbInformation, MB_OK);
  end;
end;
