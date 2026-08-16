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

### 1.10 int16 no disco e Opus na reunião — os números que decidem

**Gravação:** 16 kHz mono int16 = 32 kB/s = **115 MB/h** (345 MB numa reunião de 3 h). float32
dobraria isso e nenhum player abre sem conversão; o Whisper é alimentado pelos blocos float32 que
já estão em memória, então o disco não precisa deles.

**Compressão, medido em 3 min de áudio com forma de fala:**

- Opus a 24 kbps saiu a **23,1 kbps**: 31 MB pelas mesmas 3 h, **11x** menos que o WAV.
- **VBR `constrained`, não o VBR padrão.** Em fala os dois empatam, mas o VBR simples estourou o
  alvo em **43% (34,3 kbps)** num sinal tonal. O `constrained` mantém a promessa de tamanho.
- **PyAV, nunca o binário `ffmpeg`.** Não existe ffmpeg nesta máquina e o `.deb` não instala; o
  PyAV já entra pelo faster-whisper. Sair para o shell falharia no pior momento: logo depois de
  uma reunião de três horas.
- **O WAV só é apagado depois de o Opus ser decodificado inteiro** — todo pacote decodificado e a
  contagem de amostras comparada com a origem. Custo: **0,2 s por 3 min**, ~12 s numa reunião de
  3 h, sobre os ~97 s do próprio encode.
- **Tolerância de duração de 0,5 s.** O Opus completa o último pacote num quadro de 20 ms e carrega
  pre-skip: drift medido de **13 ms em 60 s**. Meio segundo é 30x isso e ainda pega encode
  truncado.
- O temporário é `.opus.part`, então o muxer vem de `format="ogg"` — a extensão não resolve.

### 1.11 Microfone que SOME não entrega nada — e o watchdog só era alimentado por bloco

**Sintoma:** pílula verde "Gravando", cronômetro correndo, nada gravado, nenhum alarme. É a falha
dos 99 segundos (1.1) por outra porta.

**Causa:** quando o nó do PipeWire cai (1.7) ou o USB é arrancado, o PortAudio simplesmente **para
de chamar o callback**. Nenhum bloco chega, e o watchdog só era alimentado por bloco recebido.

**Correção:** o consumidor tem timeout curto (50 ms) e, ao não receber nada, alimenta o watchdog
com zero. Do ponto de vista de quem fala, "chegou silêncio" e "não chegou nada" são o mesmo fato.
A mensagem diferencia: *"o microfone parou de responder"* em vez de *"não está captando"*.

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

---

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
