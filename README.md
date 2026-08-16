# Dito

Ditado por voz **offline**. Segure uma tecla, fale, solte: o texto aparece onde o cursor estiver.
Nada sai da máquina — o Whisper roda local.

E, o mais importante: **quando ele não está te ouvindo, ele grita.**

## O problema que este projeto existe para resolver

A versão anterior gravou 99 segundos de fala com o microfone mudo e não avisou nada:

```
transcrevendo 99.2s... (pico=0.0000 rms=0.0000)
  (nada reconhecido)  ← microfone MUDO, nao chegou audio
```

A causa raiz não é um bug de tratamento de erro — é que **não existe erro para tratar**. O
PortAudio não levanta exceção quando a captura morre; ele continua chamando o callback e
entregando zeros. Nenhum `try/except` pega isso. Só o nível do sinal pega.

Daí as duas garantias do Dito:

1. **O alarme é ao vivo, não post-mortem.** Silêncio digital dispara em ~1 s, na tela, com som.
2. **O áudio vai para o disco desde o primeiro bloco.** Se a transcrição falhar, se o modelo não
   carregar, se a colagem falhar — o `.wav` está lá, íntegro e tocável, inclusive depois de um
   `kill -9`. Dando certo, ele é apagado: o texto é a substituição, e ela é relida antes.

## Como se usa

| | |
|---|---|
| **F9** | segure, fale, solte — o texto é colado onde o cursor estiver |
| **F10** | o mesmo que o F9, **sem segurar**: aperta, fala, aperta de novo. **Sem limite de tempo** |
| Bandeja | única coisa que aparece. **Nada abre no login** |
| Janela | pelo menu ou pela bandeja: transcrições de um lado, configuração do outro |

As teclas são trocadas na tela, sem reiniciar. **As duas terminam igual:** o cartão de revisão
abre com o texto, você edita, `⏎` envia e `Tab` descarta.

No cartão há uma chave **«Guardar no Obsidian»**, desligada em toda gravação. Ligou, aquele texto
vira nota no cofre com o **título tirado do que foi dito** — sem caixa perguntando o assunto. É
opt-in de propósito: o cofre é para o que vale guardar, e uma chave que lembra do "ligado" enche
ele de tudo.

A nota é a **única** coisa que a publicação escreve: ela carrega a transcrição e aponta para a
pasta da sessão. Nada é copiado para a biblioteca.

A diferença entre as teclas é só por dentro: o F10 transcreve **em pedaços enquanto você fala**, que
é o que permite gravar uma hora sem esperar a transcrição no fim.

**Onde ficam as gravações.** Em `~/Documentos/Dito`, arquivadas por data, com o horário no nome:

```
~/Documentos/Dito/2026/08/16/07-42-13.json
```

É pasta comum, em Documentos, para você — ou qualquer programa — pegar e usar como contexto sem
saber nada do Dito. O nome é o **segundo** em que a gravação começou, então dois arquivos nunca
colidem.

**O áudio não é guardado.** Ele vai para o disco enquanto você fala — é o que salva a gravação se
o app morrer no meio — e é apagado assim que a transcrição está gravada e conferida. Só sobrevive
quando a transcrição falha ou quando nada foi captado, que é justamente quando há o que recuperar.
Uma sessão terminada ocupa **238 bytes**.

**E elas não se acumulam para sempre.** Ao abrir, o Dito varre a biblioteca e apaga o que passou de
**30 dias** (`library.keep_days`; `0` guarda tudo). A varredura é barata porque a data está no
caminho: decidir um dia inteiro custa um `strptime`, sem abrir nenhum arquivo. E ela só remove o
que o próprio app escreve — um `.md` seu na mesma pasta fica onde está.

## Comandos

```bash
dito              # abre a janela
dito listen       # sobe na bandeja, sem janela (é o que o autostart usa)
dito status       # responde na hora: ouvindo/parado, teclas, modelo e backend
dito stop
dito doctor       # microfone, mute, ganho de hardware, modelo — diz a causa e a correção
dito selftest --source zeros   # prova o alarme sem precisar de microfone
```

## Instalar

Numa máquina onde o repositório já está configurado, é uma linha:

```bash
sudo apt install dito
```

### Máquina nova — os três comandos

Copie e cole. O primeiro traz a chave que assina o repositório, o segundo aponta o apt para ele,
o terceiro instala:

```bash
curl -fsSL https://apt.defaltm.com/defaltm-archive-keyring.gpg \
  | sudo tee /usr/share/keyrings/defaltm-archive-keyring.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/defaltm-archive-keyring.gpg] https://apt.defaltm.com stable main" \
  | sudo tee /etc/apt/sources.list.d/defaltm.list > /dev/null

sudo apt update && sudo apt install -y dito
```

Depois: procure **Dito** no menu e abra uma vez. A primeira execução mostra uma tela de preparação
— ela monta a venv e baixa o modelo. Terminado isso, segure **F9** e fale.

Conferir que deu certo:

```bash
dito --version     # dito 0.3.3
dito doctor        # microfone, atalhos, modelo, colagem
```

### O que esperar

| | |
|---|---|
| Download do `.deb` | **121 KB** |
| Primeira execução: venv | **193 MB** (o que só existe no PyPI) |
| Primeira execução: modelo `small` | **464 MB**, uma vez só |
| Depois disso | roda offline, sem conta e sem servidor |

### Requisitos e limites, sem letra miúda

- **Debian 13 (trixie)** é onde isto foi construído e testado. Em Ubuntu e derivados os nomes de
  pacote das dependências podem divergir — `python3-onnxruntime` em especial pode não existir.
- **Sessão X11.** O atalho global **não funciona no Wayland** (`docs/armadilhas.md` 5.6). No
  GNOME, escolha "Xorg" na tela de login.
- **Nada abre no login** além do ícone da bandeja — o daemon sobe calado. Se a preparação ainda
  não foi feita, ele espera você abrir o app uma vez em vez de baixar centenas de MB sem janela.

### Por que o pacote é fino

O `.deb` **não** carrega Python nem Qt: declara como dependência o que o Debian já empacota, e na
primeira execução monta a venv de usuário com o que falta, numa tela com barra de progresso e
botão de tentar de novo.

O repositório apt roda em Cloudflare Pages, que **não serve arquivo acima de 25 MiB** — um pacote
auto-contido simplesmente não subiria. E `pip install` dentro do `postinst`, como root, escreve
fora do controle do dpkg e trava o apt quando falha, sem nenhuma janela para explicar.

## Usar em desenvolvimento

```bash
sudo apt install --no-install-recommends \
  python3-pyside6.qtwidgets python3-pyside6.qtsvg python3-tomli-w \
  python3-numpy python3-av python3-onnxruntime python3-pynput python3-pyperclip \
  libportaudio2 pulseaudio-utils xclip

python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/dito doctor
.venv/bin/python -m pytest
```

O `--system-site-packages` não é detalhe: é o que faz o `pip` reaproveitar o Qt, o numpy e o
onnxruntime do apt em vez de baixar ~250 MB de wheels — e é o mesmo arranjo que o `.deb` usa, para
que o que roda aqui seja o que roda instalado.

⚠️ **A venv não é relocável.** O `pyvenv.cfg` e todos os shebangs em `bin/` gravam o caminho
absoluto. Mudou a pasta de lugar, recrie a venv; não adianta mover.

## Os números, e de onde vieram

Nada aqui é chute — tudo foi medido nesta máquina (Ryzen 5 3500X, 6 núcleos, LMDE 7, X11):

| Medida | Valor | Como |
|---|---|---|
| Pico da fala | 0,036 – 0,272 | logs da versão anterior |
| Piso de ruído (H510, sala em silêncio) | 0,0038 | `dito selftest --source mic` |
| Limiar de "sem áudio" | 1e-4 | inalcançável por microfone vivo |
| Limiar de "muito baixo" | 8e-3 | acima do piso, 4,5× abaixo da fala mais fraca |
| `faster-whisper small`, CPU int8 | RTF 0,35–0,45 | 30 s → 10,35 s; 120 s → 53,70 s |

O RTF abaixo de 0,5 é o que torna possível transcrever uma reunião **enquanto** ela é gravada,
em vez de esperar ~25 minutos no fim de uma reunião de uma hora.

## Como é verificado

152 testes, e os que valem alguma coisa provam algo que não daria para afirmar de outro jeito:

- o alarme dispara em **1,03 s** contra os 99 s que a versão anterior levou;
- o áudio vai para disco desde o primeiro bloco, e o WAV abre mesmo depois de `kill -9`;
- o chunker recebe **3 horas** de fala contínua sem nunca segurar mais que 45 s, e cada sample
  que entra sai exatamente uma vez;
- os três ícones de bandeja se distinguem **só pela silhueta a 22 px** — cor não é acessível;
- o áudio só é apagado depois de o JSON ser relido do disco e o texto conferido;
- contraste medido **por papel** nos dois temas, com o piso escrito ao lado do motivo.

Os testes de atalho injetam teclas de verdade num servidor X de verdade, porque auto-repeat e
release fantasma só existem lá — um mock testaria o mock. `pytest -m "not x11"` pula esses.

Ver o desenho renderizado sem abrir o app: `python tools/render_ui.py`.

## Histórico

Este projeto saiu de `voice_type.py`, um arquivo único de 1136 linhas que vivia em
`~/dev/claude/tools/`. O código foi reestruturado, mas o **conhecimento** foi preservado: cada
correção difícil migrou junto com o comentário que explica por que ela existe (auto-repeat do X11,
release fantasma de teclado sem fio, `Xlib` não ser thread-safe, `malloc_trim` depois do unload).
Está reunido em [`docs/armadilhas.md`](docs/armadilhas.md).

O original permanece recuperável no histórico do repositório `dev`:

```bash
git -C ~/dev show 462877b:claude/tools/voice_type.py
```
