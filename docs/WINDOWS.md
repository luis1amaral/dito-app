# Dito no Windows — Estado de Paridade e Guia de Produção

Documento de referência para a versão Windows do Dito após as evoluções da série **1.6.x**.
O objetivo é alinhar tudo o que mudou no Linux com a base Windows para garantir que o projeto
esteja **100% pronto para produção** na máquina Windows.

---

## 1. Arquitetura no Windows

* **Flutter Desktop (Windows x64)** com interface fluida e design baseado em tokens (`lib/ui/tokens.dart`).
* **Motor Whisper Nativo in-process**: C++ nativo compilado via FFI (`packages/dito_whisper/`), executado em isolate dedicado (`whisper_worker.dart`) para isolamento do contexto CUDA/CPU. Sem dependência de Python.
* **Plugin de Plataforma (`packages/dito_win32/windows/`)**:
  - Hook de teclado global de baixo nível (`WH_KEYBOARD_LL` em `key_hook.cpp`).
  - Gerenciamento de foco (`ForceForeground`, `AttachThreadInput`, `SetForegroundWindow`).
  - Injeção de teclas via `SendInput` (`input.sendCtrlV`, `input.sendEnter`, `input.sendChord`).
  - Bandeja do sistema nativa (`Shell_NotifyIcon` em `tray.cpp`).
* **Captura de Áudio**: Backend WASAPI via miniaudio, elevado automaticamente para thread MMCSS "Pro Audio".

---

## 2. Impacto das Mudanças Recentes (Linux 1.6.0 a 1.6.8) no Windows

| Versão | O que mudou no projeto | Impacto / Ação necessária no Windows |
|---|---|---|
| **1.6.0** | **Sub-janela única** (HUD e Cartão de Revisão na mesma janela) | No Windows, a sub-janela nasce com `WS_EX_NOACTIVATE` (`desktop_multi_window/windows/`). Ao abrir o cartão de revisão, o app pede foco de teclado (`focus.take`). Ao fechar, o foco é devolvido à janela anterior (`focus.giveBack` via `ForceForeground`). Garantir que `WS_EX_NOACTIVATE` não bloqueie o foco explícito do cartão. |
| **1.6.1** | **Padronização de Caminhos** | O caminho de salvamento usa `Platform.pathSeparator`. No Windows, gravações moram em `%USERPROFILE%\Documents\Dito\YYYY\MM\DD\<HH-MM-SS>.json`. |
| **1.6.4** | **Remoção de WAV em disco** | O Dito **não grava mais WAV em disco** na biblioteca em produção (apenas o JSON com o texto transcrito). Para depurar áudio no Windows, define-se `DITO_SALVAR_WAV=1`. |
| **1.6.5** | **Alarme de Silêncio com Histerese** | A máquina de estado do watchdog de áudio e aquecimento por tempo (1,2 s) roda no Dart (`alarm_policy.dart` e `dito_controller.dart`). No WASAPI, verificar se dispositivos Bluetooth / USB entregam áudio válido após retorno de suspensão. |
| **1.6.7** | **Tratamento do Enter no Cartão de Revisão** | `review_card.dart` unificou `onChanged` e `_onKey` para evitar que o primeiro Enter quebre linha. No Windows, o primeiro Enter envia o texto imediatamente; Shift+Enter continua quebrando linhas. |
| **1.6.8** | **Colagem no Terminal e GUI** | No Windows, `SendInput` enviando `Ctrl+V` funciona universalmente tanto para janelas normais (WhatsApp, Word, VS Code, Discord) quanto para o **Windows Terminal, PowerShell e CMD**. |

---

## 3. Checklist de Produção no Windows

### 3.1 Ambiente e Ferramentas Necessárias
1. **Windows 10 ou 11 (64-bit)**.
2. **Visual Studio 2022** (com a carga de trabalho *Desenvolvimento para desktop com C++*, incluindo MSVC v143 e Windows 10/11 SDK).
3. **Flutter SDK 3.x** com suporte a Windows Desktop habilitado (`flutter config --enable-windows-desktop`).
4. **Inno Setup 6** instalado (usado por `packaging/windows/dito.iss` para gerar o instalador `.exe`).
5. **CUDA Toolkit 12.x** (opcional, para compilar a aceleração por GPU NVIDIA).

### 3.2 Compilação e Empacotamento
Executar no PowerShell na raiz do repositório:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
```

O script executa automaticamente:
1. **Portão de Qualidade**: `flutter analyze` e `flutter test --exclude-tags live`.
2. **Build de Release**: `flutter build windows --release`.
3. **Geração do Instalador Inno Setup**: `build\windows\installer\dito-<versao>-setup.exe`.
4. **Geração do ZIP para Auto-Update**: `build\windows\installer\dito-<versao>.zip`.
5. **Cálculo de Hashes**: `build\windows\installer\SHA256SUMS.txt`.

### 3.3 Diretórios de Instalação e Dados no Windows
* **Binários**: `%LOCALAPPDATA%\Programs\Dito\` (instalação por usuário, não exige privilégios de Administrador / UAC).
* **Configuração**: `%APPDATA%\dito\config.toml`.
* **Logs**: `%LOCALAPPDATA%\dito\logs\` (`app.log`, `controller.log`, `engine.log`, `native_engine.log`, `hotkeys.log`, `paste.log`, `crash.log`).
* **Biblioteca de Transcrições**: `%USERPROFILE%\Documents\Dito\YYYY\MM\DD\<HH-MM-SS>.json`.
* **Inicialização com o Sistema**: Registro em `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` com o comando `dito_app.exe --startup` (inicia minimizado na bandeja).

---

## 4. Roteiro de Validação na Máquina Windows

Antes de lançar uma versão de produção para Windows, valide os seguintes pontos:

### 4.1 Testes Automatizados e Espinhos Nativos
1. **Portão Geral**:
   ```powershell
   flutter analyze
   flutter test
   ```
2. **Espinho de Foco (`spike_focus.dart`)**:
   ```powershell
   flutter build windows --debug --target=tool/spike_focus.dart
   .\build\windows\x64\runner\Debug\dito_app.exe
   ```
   *Veredito esperado:* `VEREDITO .................... PASSA`.
3. **Espinho de Colagem (`spike_paste.dart`)**:
   ```powershell
   flutter build windows --debug --target=tool/spike_paste.dart
   .\build\windows\x64\runner\Debug\dito_app.exe
   ```
   *Veredito esperado:* `VEREDITO .................... PASSA` (com acentuação em pt-BR preservada).

### 4.2 Testes Manuais de Uso Real
1. **F9 (Push-to-Talk)**: Focar no Bloco de Notas ou VS Code, segurar F9, falar, soltar → o texto deve ser colado diretamente.
2. **F10 (Modo Toggle / Gravação sem Segurar)**: Pressionar F10, falar, pressionar F10 novamente → o Cartão de Revisão abre com o texto transcrito.
3. **Envio pelo Cartão**: Pressionar **Enter** no cartão → o foco deve retornar para a janela anterior e colar o texto no primeiro toque.
4. **Quebra de Linha**: Pressionar **Shift+Enter** no cartão → insere nova linha sem enviar.
5. **Windows Terminal**: Focar no Windows Terminal / PowerShell, ditar via F9 → o texto deve ser colado normalmente.
6. **Alarme de Microfone Mudo**: Desativar o microfone nas configurações do Windows e tentar gravar → a pílula deve exibir o alerta visual em ~1 s.
7. **Instância Única**: Tentar abrir o Dito uma segunda vez → a segunda instância deve focar a janela existente e encerrar.
8. **Auto-Updater**: Confirmar que o `defalt_updater` consulta `https://dito-api.defaltm.com/api/app/latest` sem erros de rede.

---

## 5. Armadilhas Específicas do Windows

1. **`WS_EX_NOACTIVATE` na Janela de HUD**:
   - A janela flutuante precisa nascer com `WS_EX_NOACTIVATE` para nunca roubar foco do aplicativo que o usuário está utilizando.
   - Ao abrir o cartão de revisão, o foco deve ser requisitado explicitamente via `SetForegroundWindow`.
2. **`AttachThreadInput`**:
   - Para transferir o foco de volta à janela do usuário (`ForceForeground`), o Windows exige anexar as threads de entrada. Sempre garantir que `AttachThreadInput(mine, owner, FALSE)` seja executado no retorno.
3. **Arquiteturas CUDA**:
   - Ao compilar com suporte a GPU, use `CUDA_ARCHITECTURES="61;75;86;89"` (código real de arquitetura, nunca apenas código virtual/PTX) para evitar travamento de compilação JIT no primeiro uso.
4. **DLLs Redistribuíveis**:
   - O instalador Inno Setup (`dito.iss`) deve incluir todas as DLLs de runtime necessárias (`msvcp140.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`) ou garantir o Visual C++ Redistributable instalado.
