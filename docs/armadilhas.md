# Armadilhas

Cada item aqui custou depuração. A maioria veio do `voice_type.py`, o arquivo único de 1136 linhas
que originou este projeto; alguns foram medidos durante o refactor. **Nenhum é hipótese** — todos
têm o sintoma observado e, quando existe, o número que provou.

Se você for "limpar" alguma coisa que parece redundante neste código, procure aqui antes. Boa parte
do que parece exagero é cicatriz.

---

## 1. Áudio

### 1.1 O PortAudio NÃO levanta exceção quando a captura morre

**Sintoma:** `transcrevendo 99.2s... (pico=0.0000 rms=0.0000)` → `(nada reconhecido)`.
99 segundos de fala perdidos, sem uma linha de traceback.

**Causa:** o stream continua "saudável" do ponto de vista da API. O callback segue sendo chamado no
ritmo certo, só que com todas as amostras em zero.

**Consequência de projeto:** detecção de falha de microfone **não pode** depender de `try/except`.
Não existe exceção para capturar. O único detector confiável é o nível do sinal — é por isso que
`audio/level.py` existe e não é opcional.

### 1.2 O ganho de captura do ALSA é um ponto cego do `pactl`

**Sintoma:** o PipeWire reporta 94% de volume, `Mute: no`, e nada chega. Já aconteceu nesta
máquina, com o controle de hardware por baixo em `Capture 0 [0%]`.

**Prova reproduzida durante o refactor:**

```
amixer -c 2 sset Mic,0 0% cap      # zera só o ganho de HARDWARE
pactl get-source-mute @DEFAULT_SOURCE@   -> Mute: no      ← cego
pactl get-source-volume @DEFAULT_SOURCE@ -> 100%          ← cego
dito selftest --source mic               -> pico 0.0001, ALARME em 1,12s
```

**Correção:** `amixer -c <card> sset Mic,0 100% cap`. O `dito doctor` detecta e imprime o comando
já com o card certo. O card sai da propriedade `alsa.card` da fonte em `pactl list sources` —
**adivinhar o card seria pior que não checar**, porque reportar o ganho da placa-mãe enquanto a
pessoa grava no headset é uma resposta errada dita com confiança.

**Portanto são três camadas, não duas:** `pactl` (mute/volume do software) → `amixer` (ganho de
hardware) → nível do sinal. As duas primeiras dão a **mensagem certa e acionável**; só a terceira
dá a **verdade**.

### 1.3 Fone sem fio pode mutar sem o servidor saber

A fonte do H510 declara `HW_MUTE_CTRL`, então o mute que passa pelo HID aparece no `pactl`. Mas o
mute feito no dongle/firmware pode não passar — o servidor segue dizendo `Mute: no` e entrega
zeros. Mais um motivo para o nível ser a verdade final.

### 1.4 O `wave` da stdlib só grava os tamanhos no `close()`

**Sintoma:** processo morto no meio da gravação deixa um `.wav` cujo cabeçalho declara **zero
frames**. Os bytes de áudio estão no arquivo e nenhum player abre.

Isso destrói a razão de ser da gravação em disco. Por isso `audio/writer.py` escreve os 44 bytes do
cabeçalho RIFF na mão e corrige os dois campos de tamanho (offsets 4 e 40) a cada flush — o arquivo
é válido **a qualquer instante**, inclusive depois de `kill -9`.

**Os tamanhos são corrigidos a CADA BLOCO, não a cada `fsync`.** Com o patch só no intervalo de
`fsync` (5 s), toda gravação mais curta que isso continuava com `RIFF=0`/`data=0` no disco: um
`kill -9` aos 4 s produzia arquivo que nenhum player abre. Um ditado dura tipicamente **2 a 5
segundos** — ou seja, a garantia era falsa justamente no caso comum. O custo de corrigir por bloco
é duas escritas de 4 bytes na page cache; o caro é o `fsync`, e esse continua no intervalo.

Vale lembrar de onde vem a regra: a versão antiga guardava a gravação inteira numa lista Python e
só tocava o disco **depois** que a transcrição dava certo. Quando ela não devolvia nada, o áudio
saía de escopo e sumia (ver 1.1).

### 1.5 A flag `status` do callback estava sendo descartada

`def cb(indata, frames, t, status)` com `status` ignorado: todo overflow de buffer e todo erro de
dispositivo sumiam sem rastro. `audio/capture.py` conta os overflows; três deixam de ser azar e
viram o aviso de "áudio picotado".

### 1.6 Piso de ruído mede 0,0038 — o limiar de "baixo" tem que ficar acima disso

Medido com `dito selftest --source mic` numa sala em silêncio, headset H510. A fala registrada nos
logs vai de 0,036 a 0,272.

- Limiar de "muito baixo" = **8e-3**: acima do piso, 4,5× abaixo da fala mais fraca.
- Limiar de "sem áudio" = **1e-4**: inalcançável por microfone vivo.

E o alarme âmbar é **condicionado a nunca ter chegado som**: sem essa trava, pausar 2,5 s no meio de
um ditado acusa "áudio muito baixo", que é falso positivo puro. O vermelho continua sempre armado,
porque zeros **depois** de fala real significam dispositivo que morreu no meio da frase.

### 1.7 Nunca abrir o dispositivo ALSA cru (`hw:`)

**Sintoma:** gravação que nunca termina, `(curto demais)` ao segurar por segundos, ou o fone fica
sem som. O nó do headset caiu do PipeWire — confirmar com `wpctl status` mostrando `Sources:`
vazio.

**Correção:** `systemctl --user restart pipewire pipewire-pulse wireplumber`.
**Prevenção:** usar sempre `default` (compartilhado).

### 1.8 O `default` do sistema pode apontar para uma entrada morta

A entrada da placa-mãe em vez do headset. Sintoma no log: `pico=0.0000`. Correção: configurar o
dispositivo por **pedaço do nome** (`H510`), não por índice — índice muda quando um USB entra ou
sai.

### 1.9 Um transiente de 100 ms travava `ever_heard` e desarmava o alarme âmbar

**Sintoma:** gravação inteira sem nada reportado e nada transcrito — o alarme âmbar, que deveria
ter gritado, ficou calado.

**Causa:** `ever_heard` era ligado no **primeiro** bloco acima do limiar. Uma tecla batendo no
instante em que a hotkey desce já passa de 8e-3, e como o alarme âmbar é condicionado a "nunca ter
chegado som" (1.6), esse único bloco desarmava o aviso pelo resto da sessão.

**Número medido, numa gravação real:** 2 blocos de 40 acima do limiar (**0,019** e **0,0098**),
pico mediano **0,00069** — piso de ruído puro.

**Correção:** só conta som **sustentado**. São necessários `clear_ms = 200 ms` contínuos acima do
limiar para ligar `ever_heard` e limpar o estado.

### 1.10 int16 no disco: 32 kB/s, e por que não float32

16 kHz mono int16 = 32 kB/s = **115 MB/h**. float32 dobraria e nenhum player abre sem conversão;
o Whisper é alimentado pelos blocos float32 que já estão em memória, então o disco não precisa
deles.

Esse número é o que motivou a decisão de 8.2: o áudio é rede de segurança, não arquivo.
A compressão para Opus chegou a existir (23,1 kbps medidos, 31 MB por 3 h) e foi **removida** junto
com a retenção — sem áudio guardado, não há o que comprimir. Está no histórico do git.


### 1.11 Microfone que SOME não entrega nada — e o watchdog só era alimentado por bloco

**Sintoma:** pílula verde "Gravando", cronômetro correndo, nada gravado, nenhum alarme. É a falha
dos 99 segundos (1.1) por outra porta.

**Causa:** quando o nó do PipeWire cai (1.7) ou o USB é arrancado, o PortAudio simplesmente **para
de chamar o callback**. Nenhum bloco chega, e o watchdog só era alimentado por bloco recebido.

**Correção:** o consumidor tem timeout curto (50 ms) e, ao não receber nada, alimenta o watchdog
com zero. Do ponto de vista de quem fala, "chegou silêncio" e "não chegou nada" são o mesmo fato.
A mensagem diferencia: *"o microfone parou de responder"* em vez de *"não está captando"*.

### 1.12 A lista de entradas oferecia aparelho que a captura a 16 kHz nunca abre

**Sintoma:** F9 respondia *"microfone indisponível: Invalid sample rate"* em toda tentativa, com o
microfone perfeito no resto do sistema — o mesmo mic gravava normalmente no navegador.

**Causa:** `list_inputs()` devolvia todo aparelho com canal de entrada, e a tela oferecia todos.
Nesta máquina eram quatro: `ALC887-VD Analog (hw:1,0)`, `ALC887-VD Alt Analog (hw:1,2)`, `pipewire`
e `default`. Os dois primeiros são acesso ALSA cru (1.7) e **não fazem 16 kHz** — a taxa fixa do
Whisper. Medido: `check_input_settings(samplerate=16000)` responde `PaErrorCode -9997` nos dois.
Ou seja, metade das opções oferecidas era impossível, e eram justamente as com nome de microfone;
`pipewire` e `default` parecem opção genérica e são as únicas que funcionam. Pior: o headset USB
que o dono realmente usa **não aparece na lista** — nesta máquina ele só existe atrás do PipeWire.

O `preflight` passava porque só perguntava se o aparelho *existe* (`missing()`), e ele existe. A
recusa vinha depois, do `Capture.start()`, com o texto cru do PortAudio.

**Correção:** três camadas.

1. `supports_rate()` pergunta ao PortAudio se o aparelho abre em `SAMPLE_RATE` — 0,1 ms quando a
   resposta é não, 18 ms quando é sim.
2. A tela só oferece o que abre (`list_usable_inputs()`). O aparelho fixado que **não** abre
   continua listado, rotulado *"não grava a 16 kHz"*: sumir com ele em silêncio reescreveria a
   configuração do dono no instante em que a tela abre.
3. O `preflight` sonda **só quando há aparelho fixado** — o caminho padrão custa 30 ms e não pode
   pagar mais 18 por tecla. A recusa passa a ter motivo e conserto, não `errno` de biblioteca.

---

## 2. Teclado no X11

### 2.1 Auto-repeat entrega pares Release+Press — o release não é confiável

Segurando a tecla, o X11 emite `Release` seguido de `Press` a poucos milissegundos de distância.
Tratar o primeiro `Release` como "soltou" mata a gravação meio segundo depois de começar.

**Correção:** não confiar no evento. Consultar o **estado físico** com `Xlib.query_keymap()` e só
finalizar depois que a tecla ficar **continuamente** solta por uma janela de carência (0,30 s).
Teclas sintéticas do XTest também aparecem no keymap, então o método é consistente.

### 2.2 Release fantasma de teclado sem fio

Teclado sem fio emite release espúrio (economia de energia) que **o próprio keymap confirma**. Isso
partia uma frase em duas gravações. A vigia "atravessa" o fantasma e mantém o **mesmo** stream.

### 2.3 `Xlib.Display` não é thread-safe

**Sintoma:** travamento. Cada release do auto-repeat criava um timer que caía em `query_keymap`;
sem serialização, duas respostas se intercalam na mesma conexão e a coisa pendura.

**Correção:** lock em volta de toda chamada, ou uma conexão por thread. Nunca as duas coisas pela
metade.

### 2.4 Round-trip do X na thread da interface congela a interface

**Sintoma:** o badge congelava. **Bissectado:** 120 ciclos de estado passam sem o grab de foco e
travam com ele.

**Causa:** dar e devolver foco exige round-trip (é preciso ler quem tinha o foco antes), e
round-trip na thread do loop gráfico bloqueia o desenho.

**Correção:** uma thread dedicada, com **conexão X própria**, só para foco. Se o X pendurar essa
conexão, a thread fica presa — a interface e a gravação, não.

### 2.5 `sync()` num caminho quente dá deadlock; `flush()` não

`sync()` espera resposta. Requisições que não precisam de resposta (como aplicar a máscara de canto
arredondado) devem usar `flush()`, que envia e não bloqueia.

### 2.6 `suppress_event` do pynput é só do Windows

No X11 a tecla de cancelar **vaza para dentro do campo de texto** — digita um espaço no meio do que
você está escrevendo. A saída é `XGrabKey`, que consome a tecla de verdade.

Não existe API de "quem é o dono desta tecla": **tentar o grab é o teste**. Se o X responde
`BadAccess`, outro programa já tem a tecla.

### 2.7 Nunca transcrever dentro do callback do teclado

O hook de baixo nível fica bloqueado enquanto o callback roda, e o Windows **remove** um listener
que demora a retornar. Todo trabalho pesado vai para uma fila.

### 2.8 O grab morre quando o NumLock ou o CapsLock liga

**Sintoma:** o atalho funciona, alguém encosta no NumLock, e a tecla volta a vazar para dentro do
campo de texto (o sintoma de 2.6, de volta).

**Causa:** `XGrabKey` casa a máscara de modificadores **exata**. As travas entram na máscara do
evento: com o NumLock ligado, a tecla que chega não é `F9`, é `Mod2+F9` — e esse grab ninguém pediu.

**Correção:** registrar o grab para **todas as combinações das três travas**, e não só para a
máscara zero. São `Lock` (0x02, CapsLock), `Mod2` (0x10, NumLock) e 0x40 (ScrollLock): 2³ = **8
combinações**, que é exatamente a tupla `_IGNORED` de `hotkeys.py`.

O `ungrab` tem que percorrer as mesmas 8 — soltar só a máscara zero deixa sete grabs pendurados no
root até o processo morrer. E o teste de dono (2.6) precisa de `sync()` depois do lote: o
`BadAccess` chega assíncrono, e sem o `sync()` o `CatchError` ainda está vazio quando é lido.

### 2.9 Fechar a conexão X com a vigia rodando abandona a gravação em curso

**Sintoma:** sair do app segurando a tecla de ditar perdia a gravação — nem colava, nem salvava.

**Causa:** `stop()` fechava o `Listener`, o `KeyGrabber` e o `KeyState` de imediato. A vigia de
`_watch_hold` continua chamando `state.is_down()` a cada `POLL_S = 0,05 s` numa conexão X que
acabou de ser fechada: a exceção mata a thread dentro do `while`, o `on_stop` **nunca é chamado**, e
a sessão fica aberta para sempre.

**Correção:** a ordem no `stop()` não é decorativa. Primeiro `_shutting_down = True` — a vigia
enxerga a flag, **quebra o laço e finaliza a gravação** em vez de abandoná-la — depois
`watcher.join(timeout=GRACE_S + 1,0 s)`, e **só então** listener, grabber e a conexão X são
fechados. Um segundo a mais que a carência de 2.1, porque é o tempo máximo que a vigia pode levar
para decidir sozinha.

### 2.10 Não derrubar e recriar o `Listener` do pynput

**Sintoma:** depois de mexer nos atalhos, a tecla ficava "presa": o app achava que a gravação
continuava, ou o atalho seguinte não fazia nada.

**Causa:** destruir o `Listener` enquanto uma tecla está pressionada perde o `Release` — o `Press`
foi visto, o par nunca chega, e `_active` fica travado no nome da ação. O listener novo sobe num
estado que não corresponde ao teclado real.

**Correção:** `pause()` **não** destrói nada. O listener continua vivo e descarta os eventos
(`if self._paused: return`); o que sai de cena é só o `XGrabKey`, via `ungrab_all()`. Assim a tecla
volta a chegar no Qt (é disso que 7.10 depende) sem que ninguém perca a contabilidade de quem está
pressionado.

---

## 3. Modelo e memória

### 3.1 `malloc_trim(0)` depois de descarregar o modelo

**Sintoma medido:** sem ele, a RSS **crescia** de 378 MB para 606 MB depois do unload. Liberar não
é devolver: a glibc mantém a arena até mandarem devolver.

### 3.2 O erro de cuBLAS só aparece no primeiro encode

Construir o `WhisperModel` com `device="cuda"` **não toca** em cuBLAS/cuDNN. Se a DLL estiver
faltando, o construtor passa e o erro só estoura na primeira transcrição — quando o fallback para
CPU já não roda mais.

**Correção:** forçar um encode de 1 segundo de zeros logo depois de construir, dentro do `try`.

### 3.3 Windows: o `pip` põe cuBLAS onde o Windows não procura

As DLLs ficam em `site-packages/nvidia/*/bin`. E `os.add_dll_directory` **não basta**: ele só cobre
`LoadLibraryEx` com as flags de diretório de busca, e o ctranslate2 resolve cuBLAS com um
`LoadLibrary` simples, que lê o `PATH` e nada mais. É preciso prefixar o `PATH` também.

### 3.4 faster-whisper não é seguro para chamada concorrente

Um preview ao vivo e o passe final sobre o mesmo `WhisperModel` corrompem os dois resultados. Não
há trava interna na biblioteca: o `RLock` de `stt/engine.py` é **toda** a proteção, e por isso ele
cobre `load`, `transcribe` e `unload` inteiros.

### 3.5 Reunião é transcrita em pedaços de 20-45 s cortados no silêncio

Duas coisas obrigam o corte:

- **Memória plana.** A versão antiga acumulava cada bloco numa lista e concatenava no fim: 3 h de
  float32 a 16 kHz seriam gigabytes de RAM.
- **A espera no fim tem que sumir.** Medido: `small` em CPU int8 roda a **RTF 0,35-0,45**.
  Transcrever só no fim custa **~25 min para 1 h** de reunião; transcrevendo durante sobra **2,2x**.

**Onde cortar importa.** O encoder do Whisper trabalha em janelas de 30 s, então 20 a 45 s
amortizam bem. O corte cai no silêncio: de preferência numa pausa real (600 ms abaixo de 0,01) e,
ao bater o teto, no ponto mais quieto dos últimos 5 s.

### 3.6 A contrapressão não pode bloquear a thread que escreve o disco

**Sintoma medido:** com a transcrição travada, o WAV parou de crescer aos 2 s enquanto o usuário
falou mais 18 s.

**Causa:** `_submit` chamava `put` com timeout e depois um `put` sem teto — **de dentro do
consumidor que escreve o WAV**. Fila cheia, consumidor parado, gravação parada.

**Correção:** `put_nowait`; o que não couber vai para um backlog em memória e é transcrito no fim.
Texto atrasado é aceitável, áudio perdido não.

### 3.7 Nada chamado do loop do Qt pode esperar um lock de thread de trabalho

**Sintoma medido:** `unload_if_idle`, que roda num `QTimer` de 60 s na thread do Qt, bloqueou
**1,90 s** num teste — e numa reunião real o `transcribe` segura o mesmo lock por **16 a 20 s**
por trecho (45 s de áudio a RTF 0,35–0,45).

**Consequência:** a pílula, a onda, o cronômetro e a bandeja congelam nesse tempo. Pior: o
`AudioAlarm` é entregue por `QueuedConnection` e desenhado nessa mesma thread — o alarme de
**SEM ÁUDIO, que o produto promete em ~1 s, ficava na fila atrás de uma transcrição.** É a
armadilha 2.4 (round-trip na thread da interface) reencarnada em outro recurso.

**Correção:** checar **antes** de travar, e usar `acquire(blocking=False)`. Ocupado é, por
definição, não-ocioso: desistir é a resposta certa, esperar não é.

**Regra geral:** nada chamado de dentro do loop do Qt pode adquirir um lock que uma thread de
trabalho segura por segundos.

---

## 4. Colagem e clipboard

### 4.1 Colar pelo clipboard, não digitar caractere a caractere

Texto em pt-BR com acento sai errado quando digitado sinteticamente. O caminho é
`clipboard + Ctrl+V`.

### 4.2 O Enter precisa esperar a colagem chegar

Sem uma pausa (~0,25 s) entre o Ctrl+V e o Enter, o Enter chega antes do texto e envia um campo
vazio.

### 4.3 Restaurar o clipboard anterior — depois

O conteúdo que estava no clipboard é devolvido com um atraso de ~1 s. Restaurar na hora corre com
a aplicação que ainda está lendo o clipboard durante a colagem.

### 4.4 `pyperclip` no Linux precisa de `xclip`

Sem ele, `paste()` levanta exceção e — na versão antiga — o texto transcrito era **perdido**, com
uma linha no `.voice.err` como único vestígio.

### 4.5 Terminal cola com Ctrl+Shift+V

O alvo do ditado é campo de texto de aplicação ou navegador. Para terminal, ditar sem colar e
copiar do log.

---

## 5. Processo e ambiente

### 5.1 A trava de instância única é um contrato ENTRE REPOSITÓRIOS

O nome `defalt-voice-input` (socket UNIX abstrato no Linux, mutex `Local\defalt-voice-input` no
Windows) é **compartilhado de propósito** com o projeto irmão `defalt`. Renomear de um lado só faz
os dois rodarem juntos, brigando pelo microfone e colando cada frase duas vezes — exatamente o bug
que a trava existe para impedir.

**Não renomeie.** Há um teste que quebra se alguém "limpar" o nome.

### 5.1b A trava do código antigo NUNCA funcionou — o retorno era descartado

Descoberto durante o refactor, e vale por si só. Em `voice_type.py:1120`:

```python
if not args.selftest:
    claim_single_instance()      # <- o socket devolvido não é guardado em lugar nenhum
```

A função faz `bind` num socket UNIX abstrato e **devolve** o socket. Como ninguém guarda a
referência, o CPython coleta o objeto no instante seguinte, o socket fecha, e o nome abstrato é
liberado pelo kernel. Provado na prática: com o ditado antigo rodando, o Dito novo conseguiu tomar
a mesma trava, e `ss -x -l | grep defalt-voice-input` não mostra nada.

Ou seja: durante todo esse tempo, dois ditados poderiam rodar juntos brigando pelo microfone e
colando cada frase duas vezes — que é exatamente o que a trava existia para impedir.

**Uma trava de recurso só vale enquanto alguém segura o objeto.** No Dito o socket vive em
`DitoApp._lock` pelo processo inteiro, e há um teste que prova que a trava rejeita a segunda
tentativa.

### 5.2 Arquivo de PID fica órfão

O supervisor sobe o processo e não escreve o PID; quem escrevia era outro caminho de inicialização.
Resultado observado: o arquivo dizia `117814` enquanto o processo real era `1812`. O que impedia a
duplicação era a trava do kernel, não o arquivo.

Por isso o controle aqui é por **socket** em `$XDG_RUNTIME_DIR`, não por PID file.

### 5.3 Matar o processo filho faz o supervisor religar

O `voice-run.sh` religa em 3 segundos. A ordem correta é **supervisor primeiro**:

```bash
kill <pid-do-voice-run.sh> && kill <pid-do-python>
```

É isso que explica o "eu matei e ele voltou sozinho".

### 5.4 As variáveis `XDG_*` podem estar definidas e VAZIAS

É o caso nesta máquina. `os.environ.get("XDG_CONFIG_HOME", padrao)` devolve `""`, e
`Path("") / "dito"` é o caminho **relativo** `dito/` — criado dentro do diretório de trabalho de
quem chamou. Todo acesso passa por `paths._xdg`, que trata vazio como ausente.

### 5.5 A venv não é relocável

`pyvenv.cfg` e todos os shebangs de `bin/*` gravam o caminho absoluto. Mover a pasta do projeto
quebra a venv em silêncio. Recriar, sempre.

### 5.6 Wayland não serve

`pynput` não escuta tecla global fora do X11. O ditado exige sessão X11.

### 5.7 `QTimer.singleShot` chamado de uma thread sem loop de eventos do Qt NÃO FAZ NADA

**Sintoma:** dois bugs que pareciam não ter relação. `dito stop` respondia **"parado."** e não
parava nada; `dito ui` com o app já rodando saía com sucesso e **não abria janela nenhuma**.

**Causa:** os comandos chegam pelo socket de controle, atendido numa thread própria. Essa thread
não tem `QEventLoop`, e `QTimer.singleShot` agenda no loop da **thread que chama** — que não
existe. O timer nunca dispara, ninguém levanta exceção, e o `return "ok"` sai antes: **a resposta é
verdadeira sobre o envio e falsa sobre o efeito.** Silêncio, que é a família de falha que este
projeto inteiro existe para combater.

**Correção:** nada de timer. O comando é roteado por um sinal Qt com
`Qt.ConnectionType.QueuedConnection` (`self.bridge.command.connect(self._run_command,
QueuedConnection)`): o Qt enfileira no loop do **objeto receptor**, que vive na thread da interface.
`_on_command` só emite; `_run_command` roda na thread do Qt, onde mexer em widget e sair do app são
operações legais.

**Regra:** de fora da thread do Qt, o único caminho é sinal com `QueuedConnection`. `singleShot`,
`widget.show()` e `QApplication.quit()` chamados de outra thread são, na melhor das hipóteses, um
no-op silencioso. Ver também 3.7, que é o problema espelhado: o que roda **dentro** do loop do Qt
não pode bloquear.

### 5.8 `/proc/PID/exe` resolve o link do venv — o instalador não matava o processo velho

**Sintoma:** `tools/instalar.sh` imprimia "Parando o Dito que está rodando" e **nenhum**
`parei o pid`. A instalação seguia, e o processo antigo continuava vivo segurando o socket de
controle e a trava de instância única (5.1). Do lado de quem usa: o pacote novo instalado, o
comportamento velho na tela.

**Causa:** o passo escolhia os candidatos pelo executável e não pelo `cmdline` — de propósito, um
`pkill -f "dito listen"` casa com o próprio shell que roda o script. Só que `/proc/PID/exe` aponta
para o **binário final**, não para o caminho invocado. O `python3` de um venv é link para o
interpretador do sistema, então medido nesta máquina:

```
cmdline = /home/luis/Desktop/Projetos/dito/.venv/bin/python3 .venv/bin/dito listen
exe     = /usr/bin/python3.13
```

O padrão era `*dito*python*|/usr/bin/python3`. O caminho com "dito" está no `cmdline`, não no
`exe`; e o Debian entrega `python3.13`, não `python3`. Nenhum dos dois casava.

**Correção:** o guarda passa a ser "é um interpretador Python?" (`*/python*`) e a identificação
continua no `cmdline`. O shell do script tem `exe=/usr/bin/bash` e continua de fora, que era o
ponto do guarda. Junto entraram duas coisas que faltavam: `KILL` para quem ignora o `TERM`, e um
aviso quando o socket continua ocupado no fim — falhar calado aqui é entregar uma instalação que
parece boa e não é.

---

## 6. Empacotamento

### 6.1 Cloudflare Pages não serve arquivo acima de 25 MiB

O `apt.defaltm.com` roda em Pages. Isso **decide** o formato do pacote: um `.deb` auto-contido
(~400 MB) simplesmente não sobe. Daí o `.deb` fino com bootstrap na primeira execução. Para um
pacote grande o caminho seria bucket R2 público, que não tem esse teto.

### 6.2 Ícone hicolor: parar em 512

1024 não renderiza. Já queimou dois projetos desta casa; está documentado no `make-deb.sh` padrão.

### 6.3 O cache do HuggingFace conta cada byte duas vezes se você seguir symlink

Os arquivos existem uma vez em `blobs/` e são linkados de `snapshots/`. `f.is_file()` segue link,
então somar ingenuamente dá o dobro — o `doctor` chegou a reportar 972 MB para um modelo de 486 MB.

### 6.4 O `.deb` fino cobra a conta na primeira execução — e ela precisa de janela

**Consequência direta de 6.1:** como o pacote não pode carregar os ~400 MB, quem baixa é o
`bootstrap.py`, na primeira execução. Três coisas que isso obriga:

- **Login nunca baixa nada em silêncio.** A entrada de autostart define `DITO_BOOTSTRAP=never` e o
  bootstrap sai com 0 sem tocar na rede. Uma barra de progresso que ninguém pediu, comendo banda
  logo depois do login, é pior que um app que só sobe quando é aberto.
- **A venv é `--system-site-packages`.** É o que deixa o pip reaproveitar o Qt, o numpy e o
  onnxruntime que vieram do apt, em vez de baixar tudo de novo dentro da venv.
- **"Pronto" é provado importando, não olhando a pasta.** `ready()` roda
  `python -c "import faster_whisper, sounddevice"` na venv (timeout de 60 s). Uma venv criada com o
  download pela metade existe no disco e não serve — e é justamente o estado em que a checagem
  ingênua diz que está tudo certo.

Sem `DISPLAY`, ou com `--headless`, o bootstrap cai para o modo texto; se a janela falhar por
qualquer motivo, ele **instala mesmo assim** pelo caminho de texto. A instalação é o objetivo, a
janela é conforto.

---

## 7. Interface

### 7.1 A sombra do Qt não pinta em janela translúcida sem moldura — a nossa é feita na mão

**Sintoma:** `QGraphicsDropShadowEffect` aplicado na pílula e no cartão de revisão não aparece. O
efeito é recortado no retângulo do widget, e num top-level com `FramelessWindowHint` +
`WA_TranslucentBackground` não há onde ele desenhar: o cartão sai com a borda dura, colado no que
estiver atrás.

**Correção:** `ui/surface.py` pinta a sombra à mão, antes do cartão. Os números:

- **9 anéis** (`SHADOW_LAYERS`), espalhamento máximo de **14 px**, deslocamento de **5 px para
  baixo** (a luz vem de cima), alpha **26** no anel mais denso.
- **Queda quadrática**, `(1 - i/9)²`. Com rampa linear os 9 anéis se leem como *nove anéis*, uma
  escada visível, e não como um borrão.

**A pegadinha que sobra é o layout.** A sombra vive **fora** do cartão, então toda janela que a usa
precisa reservar `shadow_margin() = 14 + 5 = 19 px` nas quatro margens do layout. Sem essa reserva
a sombra é recortada na borda da janela e volta a se ler como uma aresta dura — que é exatamente o
defeito que ela existia para resolver. É por isso que `overlay.py` e `review.py` somam `pad` em
`setContentsMargins` e em `setFixedWidth`.

### 7.2 A pílula NUNCA pode pegar foco; o cartão de revisão pega e DEVOLVE

São as duas metades da mesma armadilha, e elas puxam para lados opostos.

**A pílula aparece enquanto você digita.** Se ela roubar o foco, as teclas seguintes vão para ela e
não para o campo onde a pessoa está escrevendo. Por isso o conjunto de flags é obrigatório e
nenhuma delas é enfeite: `Tool` (fora da barra de tarefas e do Alt+Tab), `FramelessWindowHint`,
`WindowStaysOnTopHint`, `WindowDoesNotAcceptFocus`, `BypassWindowManagerHint`, mais
`WA_ShowWithoutActivating` — sem esta última, `show()` ativa a janela mesmo com as flags acima.

**O cartão de revisão é o oposto:** ele existe para ser digitado, então toma o foco de propósito,
pelo `FocusBroker` (thread própria com conexão X própria — 2.4), e **devolve antes de colar**. A
ordem em `_finish()` é a armadilha: se o foco voltar depois da colagem, `Ctrl+V` cai no editor do
próprio Dito e o texto some no lugar de chegar no destino.

Duas sutilezas do broker, cada uma um bug já visto: ele **nunca guarda a si mesmo** como dono
anterior (dois `take()` seguidos devolveriam o foco para o Dito), e uma exceção ao restaurar
(janela alvo fechada no meio) é engolida com `continue` — perder uma restauração é melhor que
perder a thread de foco pelo resto da sessão.

### 7.3 Token de tema na pílula é o valor errado — ela tem paleta própria

**Sintoma:** o alarme "SEM ÁUDIO" no tema escuro saía vermelho-claro sobre fundo escuro, ilegível;
o ponto de status sumia; o texto secundário sobre o vermelho virava um borrão cinza.

**Causa:** a pílula flutua sobre conteúdo arbitrário, então ela carrega **superfície própria e
escura nos dois temas** (`hud_surface = #17171c`). Um token de tema é escolhido contra o fundo do
*tema*, não contra esse fundo. Os pares que provam:

- `danger` no tema escuro é **#ff6b6f** (clareado de propósito para o fundo escuro do app). Na
  pílula o preenchimento de alarme tem que ser `hud_danger` = **#d02a30**.
- `text_inverse` **inverte** com o tema: no escuro ele é `#16161a`, e o ponto do alarme ficaria
  preto sobre vermelho. Na pílula o ponto é branco fixo.
- `hud_muted` (**#a3a3b2**) sobre o vermelho não tem contraste. Sobre o alarme o detalhe é
  `rgba(255,255,255,0.88)` e o cronômetro `rgba(255,255,255,0.75)`.

**Correções estruturais:** a paleta tem um bloco `hud_*` idêntico nos dois temas, e **toda** cor da
pílula por estado vive num lugar só (`Overlay._apply_colors`) — espalhada, sempre sobra um estado
sem revisar.

**E o piso de contraste é por papel, não 4,5 para tudo:** `content` 4,5 (AA — rótulo de botão e de
chip contam como conteúdo), `hint` **3,0** de propósito (dica com contraste de corpo deixa de
parecer dica), `control_edge` 3,0 (WCAG 1.4.11, o que se opera), `container` 1,1 (cartão contra a
página é plano, não controle). Exigir 4,5 de tudo reprova decisões corretas — e o que é reprovado
sem motivo acaba ignorado.

### 7.4 Forma: o raio é nomeado por uso, e o que precisa animar é pintado, não estilizado

**Raio.** A escala é nomeada pelo uso (`CONTROL` 8, `CARD` 12, `OVERLAY` 18), não por tamanho, e
**o raio de um filho é `externo − padding`**: um botão de raio 12 dentro de um cartão de raio 12
com 8 px de respiro deixa uma meia-lua de fundo aparecendo no canto. `PILL = 9999` é um **clamp**,
não meia altura calculada — assim ele acompanha a altura real do controle sem ninguém recalcular.

**Pintura.** O QSS não anima e não desenha geometria fracionária, então o ponto de status é um
`paintEvent`: círculo de **8 → 12 px** num cosseno de período **1,2 s**, dentro de uma caixa fixa
de **14 px**. A geometria é `QRectF` (float): com `QRect` inteiro os diâmetros fracionários do
pulso achatam o círculo e ele "treme" em vez de pulsar. Caixa fixa, não tamanho variável, ou o
layout inteiro se mexe a 60 Hz junto com o pulso.

### 7.5 Medir texto antes do layout: a largura do widget ainda não vale

**Sintoma:** o cartão de revisão abria com altura errada no primeiro texto e se corrigia com um
salto visível no segundo.

**Causa:** `_grow()` roda no `textChanged`, **antes** do layout ter atribuído geometria. Ler
`self.editor.width()` ali devolve o valor pré-layout (o tamanho padrão do widget), e perguntar ao
documento do `QPlainTextEdit` é pior ainda: ele se diagrama contra o **viewport**, e responde *uma
linha* enquanto o widget nunca foi mostrado. A conta sai errada exatamente na primeira vez, que é a
única que o usuário vê.

**Correção:** a largura útil é **calculada das constantes**, não lida do widget —
`_TEXT_WIDTH = WIDTH − 2·XL − 2·MD − 2` (o `−2` é a borda de 1 px dos dois lados). A altura sai de
`QFontMetrics.boundingRect` com `TextWordWrap | TextWrapAnywhere` (sem `WrapAnywhere` uma URL longa
estoura a medida), dividida por `lineSpacing` arredondando para cima. `lineSpacing`, não `height()`:
a diferença é o *leading*, e ela se acumula linha a linha. O teto não é um número inventado, é
**quanto ainda cabe na tela** descontando o resto do cartão (24 linhas quando nem tela há).

**E a estimativa se corrige sozinha.** Métrica de fonte e o layout real do Qt divergem por uma
linha de vez em quando, e barra de rolagem neste cartão é justamente o que não pode aparecer. Então
depois de redimensionar o código **pergunta ao widget já realizado** (`verticalScrollBar().maximum()`)
e cresce de novo — no máximo **3 passadas**, porque cada redimensionamento dispara outro layout e
um laço sem teto aqui é um congelamento na tela.

### 7.6 `QScrollArea` pinta faixas brancas entre os cartões

**Sintoma:** listra clara aparecendo entre um cartão e outro na aba de transcrições, só na área que
rola.

**Causa:** a `QScrollArea` tem **três** camadas que pintam — ela própria, o viewport e o widget de
conteúdo — e as duas de dentro herdam a cor base do estilo, não o `background` da página.

**Correção:** a regra do tema cobre os três níveis explicitamente,
`QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget { border: none; background:
transparent; }`. Estilizar só a `QScrollArea` não resolve — é por isso que o seletor parece
redundante e não é.

**Corolário no cartão de revisão:** um `setStyleSheet` local **substitui** o do app naquele widget,
então quem restiliza um `QPlainTextEdit` precisa reescrever também as regras de `QScrollBar` ali
dentro, ou o Qt volta a desenhar as setinhas padrão no meio do cartão escuro.

### 7.7 O ícone da bandeja tem 22 px: ele se distingue por FORMA, não por cor

**Sintoma:** em 22 px, "cinza parado" e "vermelho gravando" são a mesma mancha — de canto de olho,
em painel escuro, ou para quem não distingue vermelho de cinza.

**Correção:** os três estados são três **formas**: anel vazado (parado), círculo cheio (gravando),
triângulo com exclamação (alarme). A cor continua lá, como reforço, nunca como o único sinal — é a
mesma regra de 7.9 aplicada ao menor elemento da interface.

Duas coisas mais que o código carrega de propósito: o ícone é desenhado a **4× (`22 × 4 = 88 px`)**
e recebe também um pixmap de 22 px pronto, porque a redução do painel a partir de um único tamanho
grande borra a forma; e existe um **desenho de emergência** para quando o SVG não estiver instalado
— ícone faltando nunca derruba o app, ele só fica menos bonito.

### 7.8 Mola: `response` + `damping`, e Euler simples estoura a 60 Hz

Animação aqui é descrita como a Apple descreve — **tempo de resposta e razão de amortecimento** —,
não com curva de bézier: `STANDARD` 0,35 s / 1,0 (crítico, sem repique) e `MOMENTUM` 0,30 s / 0,8
(um repique só, para o que "chega" na tela). `PRESS_MS = 100` porque atraso no toque destrói a
sensação de resposta direta, `TOAST_MS = 1800` medido contra velocidade de leitura (um "Salvo" de
900 ms some antes do olho chegar) e `SHAKE_MS = 220`.

Três armadilhas no motor, todas já pagas:

- **Euler explícito estoura.** Integrar posição antes de velocidade a 16 ms (60 Hz) faz a mola
  passar do alvo em respostas curtas. O passo é **semi-implícito, velocidade primeiro**.
- **Um `QTimer` por mola desincroniza os eixos.** As molas de um mesmo movimento andam num
  `SpringDriver` só; em timers separados o X e o Y chegam em quadros diferentes e o movimento
  entorta.
- **Retarget não toca no valor atual.** Mudar o alvo no meio do voo mantém posição e velocidade, e
  é isso que faz a pílula "crescer de onde está" quando o texto muda. Recriar a animação faz ela
  saltar para o início.

A parada é por limiar duplo — **0,5 px** e **1,0 px/s** — e o valor é fixado no alvo no mesmo
quadro, ou a mola fica tremendo em torno do alvo para sempre e o timer nunca desliga.

### 7.9 O alarme não pode depender da cor — e as barras são a prova de vida

Perder fala em silêncio é a falha que originou o projeto (1.1), então o aviso é **redundante de
propósito**. Ele chega por quatro caminhos simultâneos, e cada um sozinho já falhou em teste:

- **Forma:** em `DEAD` a onda vira **uma linha reta**. "Nada está chegando" é lido sem depender de
  cor nenhuma.
- **Cor:** o preenchimento inteiro da pílula fica vermelho (`hud_danger`, ver 7.3).
- **Movimento:** um tremor de **220 ms** decaindo, longo o bastante para a visão periférica pegar,
  curto o bastante para não virar distração.
- **Fora da janela:** ícone da bandeja e notificação/som — ver 9.4.

**As barras não são enfeite: elas são o sinal de "está te ouvindo".** Por isso a escala é
comprimida, `min(1, √(rms · 18))`: o RMS de fala fica entre **0,02 e 0,10**, e num mapeamento
linear as barras ficariam praticamente invisíveis justamente enquanto tudo está funcionando. A
suavização é **0,45 por quadro** — mais rápido estroboscopa, mais lento deixa de parecer ao vivo.

### 7.10 O campo "pressione uma tecla" não enxerga a tecla que o grab está consumindo

**Sintoma:** clicar em "trocar atalho" e apertar F9 não fazia nada. Nem capturava, nem recusava.

**Causa:** o `XGrabKey` (2.6) consome a tecla **antes** de qualquer janela — inclusive a nossa. O
Qt nunca recebe o `keyPressEvent`. A funcionalidade que existe para deixar a tecla ser trocada era
justamente a que a tecla atual bloqueava.

**Correção:** capturar é um estado que **pausa os atalhos globais** (`on_capture_start` →
`hotkeys.pause()`, que solta os grabs sem matar o listener — 2.10) e os retoma no fim. Enquanto
captura, o botão chama `grabKeyboard()` do Qt para receber tudo, inclusive Tab e Escape.

Três detalhes que vieram de bug e não de gosto:

- **`focusOutEvent` encerra a captura.** Um widget que fica segurando o `grabKeyboard()` do Qt come
  **todas** as teclas da aplicação, e a única saída é fechar a janela.
- **Modificador não é recusa, é espera.** Quem vai apertar `Ctrl+F9` aperta o Ctrl primeiro;
  recusar ali dá uma mensagem de erro no meio do gesto.
- **Só teclas da tabela `BINDABLE`** viram atalho (F1–F12, Scroll Lock, Pause, Insert, Print
  Screen, Menu, Home, End, Page Up/Down, Espaço), e a mensagem de recusa **diz quais servem** — a
  tabela é a mesma que o arquivo de config, o pynput e a busca de keysym usam (ver 2.7).

### 7.11 Enter e Tab têm que ser interceptados NO campo de texto, não na janela

**Sintoma:** no cartão de revisão, Enter inseria uma quebra de linha em vez de enviar, e Tab
pulava para o botão em vez de descartar — apesar da dica na tela dizer *"⏎ envia · Tab descarta"*.

**Causa:** o evento de tecla vai primeiro para o widget **com foco**, que é o editor. `Return`,
`Enter` e `Tab` são teclas que o `QPlainTextEdit` **consome** (nova linha, navegação de foco), então
elas nunca sobem para o `keyPressEvent` da janela. O override no cartão só recebia o que o editor
deixava passar — e justamente essas três não passam.

**Correção:** a interceptação vive numa subclasse do próprio `QPlainTextEdit` (`Editor`), que
transforma as teclas em sinais (`submit`, `cancel`) e deixa o resto seguir para `super()`. Assim o
comportamento fica no lugar onde a tecla chega, e o cartão continua sem saber de teclado.

`Shift+Enter` cai no `super()` de propósito: é a quebra de linha. Sem essa exceção, texto de mais
de um parágrafo vira impossível de editar — e editar é a razão de o cartão existir.

### 7.12 A roda do mouse edita o controle por onde passa

**Sintoma:** rolar a tela de configuração trocava o valor de um `Select` no caminho — o modelo, o
microfone ou o idioma mudavam sozinhos, sem clique, e ninguém liga uma coisa à outra depois.

**Causa:** `QComboBox` e `QAbstractSpinBox` tratam a roda como "próximo item". Dentro de um
`QScrollArea` isso é destrutivo por desenho: o gesto de rolar a página é o mesmo gesto que altera o
que está sob o cursor, e o controle come o evento antes de a área rolar.

**Correção:** `Select` **nunca** aceita a roda — `event.ignore()` sempre, e o Qt propaga para a
área rolar. "Só quando tem foco" não resolve aqui: o combo *mantém* o foco depois de escolher, e a
próxima rolagem por cima dele reescreveria a escolha recém-feita. O valor muda por clique ou pelas
setas. O `Spin` aceita a roda **apenas com foco**, porque nele o passo é a interação esperada e o
foco é sempre deliberado.

---

## 8. Biblioteca e retenção

A regra dos dois lados: **ler é defensivo, apagar é estreito.** Listar errado mostra uma linha
esquisita; apagar errado destrói a única cópia do que foi dito.

### 8.1 Pasta ilegível é listada como `unknown`, nunca pulada

**Sintoma que a regra evita:** a gravação que travou é exatamente a que tem o `session.json`
corrompido — e era a única que o usuário queria de volta. Sumir com ela da lista é esconder a
evidência da falha.

Por isso cada campo tem uma segunda fonte, e nenhuma leitura levanta exceção:

- `session.json` ilegível ou que não é um dicionário → `{}`, e **o nome da pasta vira o metadado**:
  `2026-08-15_143200_meeting` já dá data, hora e modo.
- Sem `text` no metadado → as primeiras **5 linhas** do `transcript.jsonl`. É o caso da reunião que
  morreu no meio: os trechos já transcritos estão no jsonl mesmo sem o texto final.
- Sem duração → calculada do **tamanho físico** do WAV, `(bytes − 44) / (16000 · 2)`, e não do
  cabeçalho: por 1.4, o declarado subestima.
- Estado ausente → `unknown`, que é o que `recoverable()` oferece para retomar depois de um crash.

`list_sessions` também não segue symlink ao varrer (`is_dir(follow_symlinks=False)`), pelo motivo
de 6.3.

### 8.2 O áudio não sobrevive à transcrição — e a exceção é o que importa

Decisão do dono, por espaço: 115 MB/hora não se sustenta. Uma sessão é **um arquivo JSON solto**,
com data e modo no nome, e o WAV ao lado só existe **durante** a gravação.

A rede de segurança continua: o áudio vai para o disco desde o primeiro bloco (1.1), porque é o
que sobra se o app morrer no meio. O que mudou é que ele é apagado assim que existe substituição.

**E a substituição precisa ser lida antes.** O WAV só some quando o JSON foi escrito, **relido do
disco** e o texto conferido — e nunca some quando a transcrição levantou, quando nada foi captado
(`ever_heard_audio == False`) ou quando o texto saiu vazio. Sem texto não há substituição, e o
áudio é a única prova do que foi dito.

Medido: uma sessão de ditado ocupa **238 bytes** no fim, contra 160 kB de WAV durante a fala.


---

## 9. Não morrer calado

Este projeto nasceu de 99 segundos de fala perdidos sem uma linha de log (1.1). A consequência
atravessa o código: caminho de erro **nunca** pode derrubar em silêncio o mecanismo que avisa.

### 9.1 O `except` largo do consumidor de áudio é deliberado

Falha ao escrever no disco (disco cheio, pasta removida embaixo) **não pode** matar a thread
`dito-audio`: ela é quem alimenta o watchdog de nível, o único detector de microfone morto. Se ela
morre, a pílula continua verde, o cronômetro continua correndo, e o alarme que deveria gritar em
~1 s nunca sai.

Então o `try/except Exception` em volta do `writer.write` fica largo de propósito, o erro é
reportado **uma vez** (`ev.Failed` + log, com guarda para não repetir a cada bloco) e **o laço
continua**. Gravação sem disco ainda avisa; gravação sem watchdog não avisa nada.

### 9.2 Nada no `finally` do `stop()` pode levantar

**Causa:** uma exceção levantada dentro de um `finally` **substitui** a que estava em voo. Se
`writer.close()` estourar, o `ev.Failed` com o motivo real da falha de transcrição é perdido e o
usuário recebe outro erro, sobre outra coisa.

Por isso as duas operações do `finally` — fechar o WAV e `engine.unpin()` — vão cada uma no seu
`try`: a primeira loga o motivo (fechar o WAV é o último patch de tamanho de 1.4, e falhar ali
importa), a segunda é silenciosa (soltar o pin do modelo no pior caso adia um unload por 60 s).

### 9.3 Os controles de captura do ALSA têm nomes diferentes por hardware

Não existe "o" controle de captura. Em placa HDA ele costuma ser `Capture`, `Front Mic` ou
`Rear Mic`; em headset USB, `Mic` ou `Digital`. Por isso `_CAPTURE_CONTROLS` tenta os cinco e usa
os que existirem — o `amixer sget` de um controle inexistente simplesmente não retorna nada.

**Duas decisões que evitam alarme falso:**

- **Nada de `boost`.** Boost em 0% é o normal em muita placa; tratar isso como problema faria o
  `doctor` acusar erro em máquina saudável.
- **Só acusa quando TODOS os controles encontrados estão desligados ou em 0%.** Uma placa com
  `Rear Mic` mudo e `Mic` a 100% está funcionando. Alarme que grita à toa é ignorado — e aí não
  serve para o caso em que estiver certo.

O comando de correção sai montado com o card resolvido pelo `alsa.card` (1.2) e o nome do controle
que **de fato** existe naquela máquina.

### 9.4 O alarme tem três canais fora da janela, e todos são melhor-esforço

A pílula (7.9) só ajuda quem está olhando para ela. Fora dela, o alarme vai por três caminhos
independentes, porque cada um falta em alguma máquina:

1. **Ícone da bandeja** vermelho com a causa no tooltip. É a última linha de defesa: não depende de
   programa externo nenhum.
2. **Notificação** via `notify-send`, com `--urgency critical` (fica até ser dispensada) reservada
   para áudio perdido.
3. **Som** via `paplay`, na primeira trilha que existir entre `dialog-warning.oga`,
   `alarm-clock-elapsed.oga` e `bell.oga` — escolhidas por serem inequívocas, não agradáveis.

Ausência de `notify-send` ou de `paplay` é verificada com `shutil.which` e devolve `False`; o
`Popen` inteiro é `start_new_session=True` com saída para `DEVNULL`. **Nenhum canal levanta
exceção** — falhar em avisar não pode derrubar o que ainda tem chance de avisar.

**E a repetição é limitada:** som no máximo a cada **10 s**, notificação **só na primeira** vez de
cada alarme. Repetir a cada tick transforma o alarme em ruído que o usuário aprende a ignorar, que
dá no mesmo que não ter alarme.

---

## 10. Reunião: publicação e nota

### 10.1 A ordem da publicação é texto → nota, e cada etapa falha sozinha

Uma reunião de três horas termina numa sequência de operações que podem falhar de forma
independente. A regra é **primeiro o que não dá para refazer**, e nenhuma etapa aborta a seguinte:

1. **`transcricao.md`** é escrito assim que a pasta existe. É o resultado do processamento, e não
   existe em nenhum outro lugar.
2. **A nota** por último, porque é a única peça que uma pessoa consegue reescrever à mão. Falha ao
   escrever a nota vira **aviso**, não erro: a reunião continua salva.

**O áudio não passa por aqui.** Ele já está gravado na pasta da sessão desde o primeiro bloco
(1.4), e mover a única cópia de três horas de gravação como parte de um passo que pode falhar é
trocar segurança por arrumação. Compressão e o que acontece com o WAV são assunto de 1.10.

**A pasta da biblioteca é do usuário e pode estar sem permissão.** Se o `mkdir` falhar, o destino
passa a ser uma pasta dentro do espaço do próprio Dito, com aviso — a reunião não se perde por
causa de um diretório. Colisão de nome resolve com sufixo `-2`…`-99` e, esgotado, com `HHMMSS`.

**Aviso ganha da boa notícia:** a linha que aparece na pílula é o primeiro aviso, se houver, e só
"reunião salva" quando não houver nenhum. Silêncio sobre um problema é o que criou este projeto.

### 10.2 A nota sai no formato da skill `reuniao`, não num formato do Dito

O arquivo é markdown com frontmatter `data / tipo: reuniao / participantes / tags / duracao`, para
cair no cofre e ser encontrado pelas mesmas buscas que as notas escritas à mão. Detalhes que
importam:

- **Tag `dito` sempre**, marcando a nota como criada por máquina: uma busca acha todas as reuniões
  que ninguém preencheu ainda.
- **Link de volta para a gravação** por URI `file://` gerado com `Path.as_uri()`, que
  percent-encoda espaço — que é o que um link markdown precisa e o que `str(path)` não faz.
- **A transcrição bruta vai dobrada** num `<details>` no fim. Transcrição colada no corpo **não é**
  a nota: ela empurra o conteúdo escrito por gente para fora da tela.

### 10.3 O Dito NÃO resume: as seções saem vazias de propósito

`## Decidido`, `## Pendências` e `## Discutido, sem decisão` são escritas **em branco**.

Não é funcionalidade faltando, é limite de papel: **o Dito ouviu a reunião, ele não participou
dela.** Ele não sabe quem tem autoridade para decidir, o que era brincadeira, nem o que ficou
combinado no olhar. Um resumo automático numa nota que vai durar anos põe palavra na boca de gente
que estava lá — e o erro só é descoberto quando alguém cobra a pendência errada.

O que ele entrega é a matéria-prima com as seções prontas para preencher. A mesma frase está na
tela de configuração, para a expectativa nascer certa.

### 10.4 O cofre pode não existir — e o áudio não entra nele por padrão

**Cofre ausente não é erro fatal.** Se `vault_dir()` não for um diretório, a nota é escrita **junto
da gravação** e volta um motivo já em pt-BR, pronto para exibir: *"o cofre … não existe — a nota
ficou junto da gravação"*. O mesmo vale para falha de permissão ao criar a subpasta. Escrever no
lugar possível e **dizer onde foi** é sempre melhor que não escrever.

**Copiar o áudio para dentro do cofre é `false` por padrão, e esse padrão é a armadilha.** Muito
cofre do Obsidian é um repositório git com sincronização automática (Obsidian Git): ligar a cópia
faz cada reunião empurrar dezenas de MB para dentro do histórico — que nunca mais saem. Quem quer
liga com consciência; ligado por padrão, ninguém percebe até o repositório estar inchado.

### 10.5 Reservar o nome com criação exclusiva, nunca `exists()` e depois escrever

**Causa:** entre o `exists()` e o `write_text()` cabe outro processo. Perder a corrida aqui é
**sobrescrever a nota de outra reunião** — e nota sobrescrita não tem de onde voltar.

**Correção:** `path.touch(exist_ok=False)` num laço que tenta `stem.md`, `stem-2.md`, `stem-3.md`…
A criação exclusiva é atômica no sistema de arquivos: quem chegou primeiro fica com o nome, o outro
segue para o próximo.

**E o nome é reservado ANTES de montar o corpo**, porque o corpo cita o áudio ao lado dele com o
mesmo sufixo (`![[2026-08-15-reuniao-2.opus]]`). Montar primeiro e reservar depois gera nota
apontando para arquivo que não existe. Se a escrita falhar depois da reserva, o arquivo vazio é
removido (`unlink(missing_ok=True)`) e a exceção sobe — nada de nota de 0 byte no cofre.

### 10.6 O `slugify` também é a barreira contra `../`

O assunto da reunião é digitado pelo usuário e vira **nome de arquivo** dentro do cofre. Um assunto
como `../../.ssh/config` seria um caminho, não um nome.

A mesma normalização que faz `Reunião: Orçamento` virar `reuniao-orcamento` é o que fecha essa
porta: depois do NFKD sem acentos, `re.sub(r"[^a-z0-9]+", "-")` só deixa passar `a-z`, `0-9` e
hífen — **`/` e `.` não sobrevivem**, então não existe travessia de diretório nem nome oculto. Não
é validação separada que alguém pode esquecer de chamar: é a única função que produz o nome.

Dois números junto: teto de **60 caracteres**, que deixa espaço para o prefixo de data e um sufixo
`-12` de colisão (10.5) em qualquer sistema de arquivos, e assunto que sobra vazio vira
`reuniao` — nome de arquivo em branco também é um caminho inválido.
