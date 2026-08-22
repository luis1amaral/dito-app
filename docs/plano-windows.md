# Plano de Porte e Build do Windows (Sem Quebrar o Linux)

> **Instrução para Agentes e Desenvolvedores no Windows:**  
> Se você estiver em uma máquina Windows para finalizar o porte, validar ou gerar a release de produção do Dito, **siga este roteiro estritamente do início ao fim**.

---

## 1. A Regra Fundamental: Não Quebrar o Linux

O código dentro de `lib/` é **compartilhado entre Windows e Linux**.

1. **Nunca use caminhos com barra invertida fixa (`\`) no Dart:**  
   Sempre use `Platform.pathSeparator` ou `lib/config/paths.dart`.
2. **Código de plataforma fica atrás do plugin `dito_win32`:**  
   Mudanças nativas do Windows vivem em `packages/dito_win32/windows/` e `packages/dito_whisper/windows/`.
3. **Não altere a semântica do `review_card.dart`:**  
   O tratamento unificado de Enter (`_onKey` + `onChanged`) foi validado para evitar que o primeiro toque pule linha.
4. **WAV continua desligado por padrão em disco:**  
   As gravações em produção salvam apenas os arquivos de texto JSON em `Documents\Dito\`. `DITO_SALVAR_WAV=1` é apenas para depuração.

---

## 2. Pré-Requisitos na Máquina Windows

* **Windows 10 ou 11 (64-bit)**
* **Visual Studio 2022**: Carga *Desenvolvimento para desktop com C++* (MSVC v143 e Windows 10/11 SDK).
* **Flutter SDK 3.x** habilitado para desktop:
  ```powershell
  flutter config --enable-windows-desktop
  ```
* **Inno Setup 6**: Necessário para gerar o instalador `.exe`.  
  Instalação rápida via winget:
  ```powershell
  winget install JRSoftware.InnoSetup
  ```
* **CUDA Toolkit 12.x** *(Opcional)*: Se a máquina possuir GPU NVIDIA e for gerar aceleração por hardware.

---

## 3. Roteiro Passo a Passo de Execução

### Passo 1: Atualizar o Repositório
No terminal do Windows (PowerShell na raiz de `dito-app`):
```powershell
git pull origin master
```

### Passo 2: Portão Automatizado
Garantir que a base Dart está 100% íntegra:
```powershell
flutter analyze
flutter test --exclude-tags live
```
*Critério:* **Zero erros e zero falhas.**

### Passo 3: Provar o Foco Nativo no Windows
Compilar e rodar o espinho de foco:
```powershell
flutter build windows --debug --target=tool/spike_focus.dart
.\build\windows\x64\runner\Debug\dito_app.exe
```
*Critério:* A janela abre, simula o ciclo de foco e encerra exibindo `VEREDITO .................... PASSA`.

### Passo 4: Provar o Mecanismo de Colagem e Acentos
Compilar e rodar o espinho de colagem:
```powershell
flutter build windows --debug --target=tool/spike_paste.dart
.\build\windows\x64\runner\Debug\dito_app.exe
```
*Critério:* O texto com acentuação em pt-BR é inserido via `SendInput`, o clipboard anterior é restaurado e o console reporta `VEREDITO .................... PASSA`.

### Passo 5: Gerar a Release de Produção
Rodar o script mestre de compilação e empacotamento:
```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
```
Esse script executa:
1. `flutter build windows --release`
2. Compilação do instalador pelo Inno Setup (`packaging\windows\dito.iss`)
3. Criação do ZIP do bundle para auto-atualização (`build\windows\installer\dito-<versao>.zip`)
4. Geração dos hashes de segurança em `build\windows\installer\SHA256SUMS.txt`

### Passo 6: Validação Manual em Uso Real
Instalar o executável gerado (`build\windows\installer\dito-<versao>-setup.exe`) e testar:
1. **F9 (Push-to-Talk):** Segurar F9 no Bloco de Notas ou VS Code, falar e soltar → texto colado diretamente.
2. **F10 (Toggle Reunião):** Tocar F10, falar, tocar F10 → cartão de revisão abre na tela. Pressionar Enter → texto colado no primeiro toque.
3. **Windows Terminal / PowerShell:** Testar ditado com foco no terminal do Windows → texto colado normalmente.
4. **Bandeja:** O ícone do Dito deve permanecer ativo na bandeja do sistema sem abrir janelas desnecessárias.

---

## 4. O que Fazer se Encontrar Erros

* **Erro `Inno Setup não encontrado`:**  
  Instale o Inno Setup 6 (`winget install JRSoftware.InnoSetup`) ou verifique se `ISCC.exe` está no PATH / `%LOCALAPPDATA%\Programs\Inno Setup 6`.
* **Erro de DLL no Windows:**  
  O `dito.iss` já empacota o bundle completo do Flutter. Verifique se o executável roda sem pedir `VCRUNTIME140.dll` em uma máquina limpa.
* **Se precisar alterar código C++ no Windows:**  
  Altere apenas os arquivos em `packages/dito_win32/windows/` ou `windows/runner/`. Não altere os arquivos equivalentes de `linux/`.
