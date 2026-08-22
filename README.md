# Dito 🎙️

Ditado por voz **100% offline**, ultrarrápido e nativo com Whisper C++ para **Windows e Linux**.

---

## 📥 Como Instalar

### No Linux (Debian, Ubuntu, Linux Mint, LMDE)

Copie e cole no seu terminal:

```bash
# 1. Adicionar a chave de segurança
sudo curl -fsSL -o /usr/share/keyrings/defaltm-archive-keyring.gpg https://apt.defaltm.com/defaltm-archive-keyring.gpg

# 2. Adicionar o repositório
echo "deb [signed-by=/usr/share/keyrings/defaltm-archive-keyring.gpg] https://apt.defaltm.com stable main" | sudo tee /etc/apt/sources.list.d/defaltm.list

# 3. Instalar o Dito
sudo apt update && sudo apt install dito
```

---

### No Windows

👉 **[Clique aqui para baixar o Instalador do Windows (.exe)](https://github.com/luis1amaral/dito-app/releases/latest)**

Baixe o arquivo `dito-<versao>-setup.exe` e instale normalmente.

---

## 🚀 Como Usar

* **`F9` (Segurar para Falar):** Segure o F9, fale o seu texto e solte. O texto é digitado automaticamente onde o cursor estiver (WhatsApp, Word, Discord, VS Code ou Terminal).
* **`F10` (Modo Alternar / Falar sem Segurar):** Dê um toque no F10 para iniciar a gravação (ideal para ditar em pé ou longe do teclado) e outro toque para encerrar e abrir o cartão de revisão para envio.

---

## 📚 Documentação Técnica

Para desenvolvedores e manutenção do projeto:

* 🪟 **[Plano de Porte e Build do Windows](docs/plano-windows.md)** — Roteiro passo a passo para compilar e gerar a release no Windows sem quebrar o Linux.
* ⚠️ **[Armadilhas e Aprendizados](docs/armadilhas.md)** — Histórico de problemas já resolvidos e regras de ouro de plataforma.
* 🐧 **[Guia do Linux](docs/LINUX.md)** — Arquitetura X11, GTK, XTEST e empacotamento APT.
* 🪟 **[Guia do Windows](docs/WINDOWS.md)** — Arquitetura Win32, WASAPI e Inno Setup.
