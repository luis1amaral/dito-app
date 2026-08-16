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
