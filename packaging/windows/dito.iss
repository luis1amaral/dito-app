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
; Saem de tools/gen_icons.py, dos mesmos SVG da marca. Uma lista por DPI: o Inno escolhe o
; tamanho mais próximo, e num desktop a 150% a faixa continua nítida em vez de esticada.
#define WizardBig "wizard\wizard-164x314.bmp,wizard\wizard-192x386.bmp,wizard\wizard-246x459.bmp,wizard\wizard-328x628.bmp"
#define WizardSmall "wizard\wizard-small-55x58.bmp,wizard\wizard-small-64x68.bmp,wizard\wizard-small-83x80.bmp,wizard\wizard-small-110x116.bmp"

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
WizardImageFile={#WizardBig}
WizardSmallImageFile={#WizardSmall}
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
; DESMARCADA de propósito: são 1,3 GB, e quem não tem placa NVIDIA não ganha nada com eles. O .exe
; é CPU-only por construção (sem CUDA no bundle e sem pip para buscá-lo) — ver docs/armadilhas.md
; 3.11. Quem pular aqui liga depois com «dito gpu --install», nada fica sem saída.
; A explicação vai no GroupDescription porque só ELE aceita %n e quebra linha: a lista de tarefas
; do Inno não quebra, e uma descrição longa sai cortada com barra de rolagem horizontal.
Name: "gpu"; Description: "Baixar a aceleração por placa de vídeo (1,3 GB)"; GroupDescription: "Placa de vídeo:%nSó marque se esta máquina tem uma NVIDIA — a transcrição fica ~3x mais rápida."; Flags: unchecked

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
; Antes do postinstall e com waituntilterminated: o download tem que acabar enquanto o assistente
; ainda está na tela. Quem desenha o progresso é o próprio Dito (src/dito/gpu_setup.py), porque só
; ele sabe quantos bytes faltam. Falhar aqui NÃO reprova a instalação: o Dito funciona na CPU.
Filename: "{app}\ditow.exe"; Parameters: "gpu --install --window"; StatusMsg: "Baixando a aceleração por placa de vídeo (1,3 GB)..."; Flags: waituntilterminated; Tasks: gpu
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
var
  Cuda: string;
begin
  if CurStep = usUninstall then
  begin
    StopDito();
    RemoveFromPath(ExpandConstant('{app}'));
  end;
  // As gravações e a biblioteca ficam. Apagá-las seria a única perda irreversível deste programa.
  // A pasta da GPU também fica, e por isso é anunciada: 1,9 GB esquecidos em silêncio é falta de
  // educação, e apagá-la daqui quebraria a promessa de que este desinstalador não apaga arquivo.
  if (CurStep = usPostUninstall) and (not UninstallSilent) then
  begin
    Cuda := '';
    if DirExists(ExpandConstant('{localappdata}\dito\cuda')) then
      Cuda := #13#10#13#10 + 'A aceleração por placa de vídeo (1,9 GB) continua em:' + #13#10 +
              ExpandConstant('{localappdata}\dito\cuda') + #13#10 +
              'Ela é sua para apagar quando quiser.';
    MsgBox('O Dito foi removido.' + #13#10#13#10 +
           'As suas gravações NÃO foram apagadas:' + #13#10 +
           ExpandConstant('{localappdata}\dito\state') + #13#10 +
           ExpandConstant('{userdocs}\Dito') + Cuda,
           mbInformation, MB_OK);
  end;
end;
