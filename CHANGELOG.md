# CHANGELOG — Dito

## 2026-08-16 — a GPU no Linux deixou de ser promessa: o caminho existia e nunca era percorrido

### O quê
1. **`platform/linux_x11/cuda_libs.py`** (novo) — pré-carrega cuBLAS/cuDNN com
   `ctypes.CDLL(..., RTLD_GLOBAL)`, espelhando o que `platform/windows/cuda_dlls.py` já fazia lá.
2. **`stt/engine.py`** — `register_cuda_dlls()` passou a escolher o adaptador por plataforma. Antes
   importava o de Windows **sempre**, inclusive no Linux.
3. **`bootstrap.py`** — `has_nvidia_gpu()` e instalação de `nvidia-cublas-cu12` / `nvidia-cudnn-cu12`
   numa etapa própria, só quando há placa.

### Por quê
Numa máquina com GTX 1650 e driver 550 funcionando, o Dito rodava **em CPU e não dizia nada**. O
diagnóstico: `ctranslate2.get_cuda_device_count()` devolvia `1`, o `nvidia-smi` respondia, e o
`WhisperModel(device="cuda")` morria com `Library libcublas.so.12 is not found or cannot be loaded`.

São duas camadas que se confundem facilmente: o **driver** faz o sistema enxergar a placa; **cuBLAS
e cuDNN** são bibliotecas de cálculo à parte, que o driver não traz. Faltavam as segundas — e, mesmo
depois de instaladas, o `pip` as põe em `site-packages/nvidia/*/lib`, onde o linker do Linux não
procura. Detalhe em `docs/armadilhas.md` 3.8.

O `except` do `engine.py:108` capturava tudo isso e caía para CPU em silêncio. Funcionava — só que
lento, para sempre, sem sintoma. É a falha silenciosa que originou este projeto, em outro recurso.

### A regra que não foi enfraquecida
**Aceleração é bônus e falha sozinha.** O download de ~1,5 GB acontece *depois* do `ready()`, em
`_install_gpu_extras`, e um erro ali só emite "GPU acceleration unavailable — Dito will use the CPU":
quem não tem placa, não tem rede ou não tem disco continua com uma instalação de CPU que funciona.
Por isso os pacotes CUDA **não** entram no `requirements.lock`, que é obrigatório para todos.

### Como foi verificado
`ruff check` limpo nos arquivos tocados e `pytest -m "not x11"` com **245 passando**. Prova de ponta
a ponta com o venv real do Dito: `register()` carregou **17 bibliotecas**, e o
`WhisperModel('small', device='cuda', compute_type='float16')` subiu e transcreveu — o mesmo encode
forçado que antes levantava `RuntimeError`.

### Também: código morto removido
`log_file()` e `history_file()` (`paths.py`), `subscribe_events()` (`audio_system.py`) e
`ensure_ui_or_hint()` (`app.py`) saíram — 27 linhas, nenhuma com chamador. A única referência
restante a `ensure_ui_or_hint` está em `packaging/deb/build/`, que o `make-deb.sh` regenera do zero.
O import `Callable` que ficou órfão em `app.py` foi junto.

### Em aberto
O ganho de velocidade **ainda não foi medido de forma confiável**: os clipes disponíveis somavam
11,6 s e rendiam 1 palavra depois do VAD, então a comparação mediu overhead, não transcrição.
Falta refazer com ~1 min de fala real antes de afirmar qualquer número.

## 2026-08-16 — o alarme acaba junto com a gravação, e a notificação não faz mais som

### O quê
1. **A pílula vermelha some quando a gravação termina** — soltar o F9, apertar o F10 de novo,
   qualquer motivo. Quem leva a notícia de que nada foi captado é a notificação.
2. **Toda notificação sai muda** (`--hint boolean:suppress-sound:true`).
3. O teste do `kill -9` deixou de falhar por carga da máquina.

### Por quê
Regra dita pelo dono, e melhor que a minha tentativa anterior de dispensar depois de 8 s: **a
pílula vermelha pertence a uma gravação em curso.** Ela quer dizer *"você acha que está gravando e
não está"* — no instante em que a gravação acaba, a frase fica sem sujeito. Mantê-la na tela depois
disso é relatar passado como se fosse presente.

Resultado da mudança: `show_dead` passou a ter **um único** chamador — o alarme ao vivo.

**E o "som chato" não era o do Dito.** Existem duas fontes e só uma tinha interruptor: o alarme do
próprio app (`alerts.sound`) e o som que o **ambiente gráfico** toca ao exibir qualquer notificação.
Num toque acidental o alarme nem dispara, então o som ouvido era sempre o do ambiente — e desligar
a chave da tela não tinha efeito nenhum sobre ele, o que transformava aquele interruptor em mentira.
Agora toda notificação carrega a dica padrão do freedesktop que manda o ambiente exibir e calar.

O Dito continua com canal sonoro próprio, escolhido para ser inequívoco em vez de agradável, e com
o interruptor na tela funcionando de verdade.

### A regra que não foi enfraquecida
O alarme **durante** a gravação continua igual: forma, cor, movimento e som, em ~1 s. O que mudou é
só o que acontece **depois** que a gravação termina.

### Também
`test_a_short_recording_survives_kill_nine` esperava 3 s o subprocesso escrever 40 blocos antes de
matá-lo. Com a máquina carregada isso estourava e o teste falhava como se a garantia tivesse
quebrado. A espera é preparo, não medição: subiu para 15 s, e a asserção do `kill -9` não mudou.

### Como foi verificado
277 testes verdes, `ruff` limpo. Três testes novos de notificação: nenhuma usa `critical`, o alarme
dura mais que um aviso comum, e a dica de silêncio está presente. Notificação real disparada nesta
máquina apareceu sem som.

### Documentação
`docs/armadilhas.md` **9.7** (revisto) e **9.8**.

---

## 2026-08-16 — encostar no F9 sem querer não deixa mais rastro nem alarme preso

### O quê
1. Gravação com **menos de 0,6 s e sem texto** é descartada inteira — JSON, WAV e parciais — e não
   dispara alarme nenhum.
2. O alarme *"nada foi captado"* **se dispensa sozinho** depois de 8 s.

### Por quê
Apertar e soltar o F9 na hora, sem falar, deixava uma sessão no disco que não era gravação, e a
pílula vermelha presa na tela até reiniciar o app.

O alarme estava certo pelo motivo errado: `ever_heard` sai falso quando nada foi ouvido, e num toque
de 200 ms **não houve janela para ouvir** — o watchdog ignora os primeiros 300 ms de propósito,
porque o PipeWire acorda uma fonte suspensa preguiçosamente. Gravação mais curta que a grace
**sempre** termina com `ever_heard` falso, por construção; alarmar ali é falso positivo garantido.

E, diferente de 9.5, aqui a sessão existiu — mas **já tinha acabado**. A pílula relatava um fato
passado como condição em curso, e alarme que não sai ensina a ignorar alarme (9.6).

### A regra que não foi enfraquecida
Segurar a tecla e falar no vazio continua sendo a falha central do projeto. O limiar é sobre
**quanto tempo a tecla ficou apertada**, não sobre quanto áudio chegou — microfone morto com a tecla
segurada por 10 s alarma exatamente como antes, e o áudio fica, porque sem texto não há substituição.

### Como foi verificado
274 testes verdes, `ruff` limpo. Dois testes novos prendem os dois lados: toque acidental não deixa
sessão no disco, e gravação longa sem texto **continua** registrada com o áudio preservado.

### Documentação
`docs/armadilhas.md` **9.7**.

---

## 2026-08-16 — segurar o F10 ligava e desligava a gravação sem parar

### O quê
Um `TOGGLE` só age num Press que venha **depois de a tecla ter subido de verdade**. A alternância
marca a tecla como retida, e uma thread espera o **keymap físico** confirmar que ela subiu por
`GRACE_S`.

### Por quê
Segurar o F10 em vez de tocar fazia a gravação entrar e sair sem parar. No disco ficaram **cinco
sessões vazias em três segundos**, cada uma aberta e fechada antes de dar tempo de falar.

O ramo `HOLD` já se protegia do auto-repeat com `if self._active is not None: return`. O `TOGGLE`
não podia usar a mesma guarda — para ele um segundo Press **deve** alternar — então confiava em
todo Press. E o X11 entrega Press repetido enquanto a tecla está apertada (2.1).

Medido, injetando tecla num X de verdade com auto-repeat ligado: segurar 1,5 s produziu **35
eventos**, 17 pares start/stop. Com a correção, **um**.

Debounce por tempo foi descartado: janela grande o bastante para engolir o auto-repeat também
engole um toque duplo legítimo. O keymap não tem esse dilema — ele sabe se o dedo saiu.

### Junto
O link da nota do Obsidian dizia `[16]` — o nome da pasta do dia. Agora diz a data e a hora da
gravação, que é o que alguém reconhece três semanas depois.

### Como foi verificado
272 testes verdes, `ruff` limpo. O teste novo injeta tecla num X real e segura 1,5 s, bem além do
atraso de auto-repeat do servidor. **Conferido que ele reprova sem a correção**: removi o conserto,
rodei, e ele acusou os 35 eventos.

### Documentação
`docs/armadilhas.md` **2.11**.

---

## 2026-08-16 — publicar escreve só a nota, e nada mais se acumula na biblioteca

### O quê
1. **Publicar não copia mais o texto para uma pasta própria.** Escreve a nota no cofre, e ela
   aponta para a pasta da sessão que já existe.
2. `meeting.obsidian.copy_audio` **removido** — procurava `audio.wav`/`audio.opus`, nomes que nada
   escreve desde que a sessão virou um arquivo só.
3. `Published.transcript` removido; `Published.folder` passa a ser a pasta da sessão.
4. Os avisos deixaram de dizer "reunião": agora é *"Guardado no Obsidian"*.

### Por quê
Cada gravação enviada ao cofre criava `~/Documentos/Dito/2026-08-16_0753-titulo/transcricao.md`,
com o mesmo texto que o JSON da sessão já guardava. Em três dias de uso já eram três pastas.

O pior não é a duplicata: é que **a varredura de retenção nunca alcançaria** essas pastas, porque
elas não têm forma de data. O lugar onde o texto ia se acumular para sempre era justamente o que
foi criado para organizar.

A publicação nasceu antes de a sessão morar na biblioteca. Quando ela era um JSON em
`~/.local/share`, copiar o texto para Documentos **era** o que entregava o texto ao dono. Depois da
mudança de casa, virou cópia sem função.

### A regra que não foi enfraquecida
Cofre inexistente continua não sendo criado, e a nota cai ao lado da gravação com a ressalva na
tela. Ela é `.md`, e a varredura só remove o que o app escreve como sessão — uma nota salva
sobrevive à limpeza de propósito: é o que o dono pediu para guardar.

### Um erro meu, no meio do caminho
Ao traduzir as strings novas eu limpei os marcadores `fuzzy` **em bloco**. O `msgmerge` casa string
nova com velha por similaridade e marca o palpite como duvidoso justamente para um humano decidir;
limpar sem ler transformou palpite em verdade. O portão respondeu *"0 sem tradução, 0 duvidosa"*
com quatro entradas erradas — `recording saved` como *"gravando"*, `Dito — saved in Obsidian` como
*"Dito — diagnóstico"*. Corrigidas uma a uma, e a conferência final passou a ser **carregar o `.mo`
e imprimir cada string**, que é o que o app mostra. Está em `docs/armadilhas.md` **7.15**.

### Como foi verificado
271 testes verdes, `ruff` limpo, catálogo com 0 sem tradução e 0 duvidosa — desta vez conferido
pelo `.mo` carregado, string por string. `tests/test_publish.py` foi reescrito para o contrato novo:
publicar não muda o conteúdo da biblioteca, a nota carrega a transcrição e aponta para a sessão, e
o `.md` ao lado da gravação não é confundido com sessão na listagem.

### Documentação
`docs/armadilhas.md` **10.8** e **7.15**.

---

## 2026-08-16 — o áudio voltou a se apagar, o Obsidian virou escolha, e a biblioteca se limpa

### O quê
1. **O WAV é apagado de novo quando a transcrição dá certo.** Estava ficando **sempre**.
2. **Chave «Guardar no Obsidian» no cartão de revisão**, desligada em toda gravação, nas duas
   teclas. Só o que você marca vira nota no cofre.
3. **Limpeza automática:** ao abrir, o Dito remove sessões com mais de **30 dias**
   (`library.keep_days`; `0` guarda tudo).
4. **As notificações somem sozinhas** — 15 s no alarme, 6 s no resto.
5. A linha de status parou de chamar o F10 de "reunião": agora é *"segure F9 para ditar, aperte
   F10 para ditar"*.

### Por quê — o vazamento de áudio
Uma ditada de 34 s deixava 1,1 MB no disco para sempre, com a transcrição saindo perfeita. É a
regressão dos 115 MB/hora que o refactor inteiro existiu para matar.

A causa levou quatro hipóteses erradas antes de aparecer. O consumidor alimenta o watchdog em dois
lugares: quando o bloco chega, e quando o `get(timeout=_POLL_S)` expira — este último com **zero**,
para que um microfone que sumiu alarme igual a um mudo (1.11). Só que `_POLL_S` é **exatamente** o
intervalo entre blocos (800 amostras a 16 kHz = 50 ms). Numa gravação **saudável** o poll expira o
tempo todo, e cada expiração injeta silêncio falso, que zera o contador de som sustentado. Logo
`ever_heard` termina falso, e o `_discard_scratch` — que exige `ever_heard` antes de apagar — deixa
o áudio.

Medido na gravação real do dono: pico 0,106, **407 de 678 blocos** acima do limiar. Áudio ótimo,
`ever_heard=False`.

O que escondeu isso da suíte: os testes entregavam blocos a cada **5 ms**, então o poll nunca
expirava. O defeito só existe no ritmo real. Agora existe `deliver_paced`, e um teste que usa.

### Por quê — o Obsidian como escolha
Toda gravação virava nota, e o cofre ia encher de lixo. Pedido do dono: uma chave no cartão,
desligada por padrão, para marcar o que vale — assim o cofre vira contexto de projeto de verdade.
Ela reseta a cada gravação: chave que lembra do "ligado" enche o cofre de tudo, que é o problema
de origem.

Junto: fechar o app no meio de uma gravação não escreve mais nota. Não há ninguém para escolher, e
o JSON da sessão guarda o texto de qualquer forma.

### Por quê — a limpeza
Ditado se acumula e o disco enche sem ninguém perceber. A varredura é barata porque a data está no
**caminho**: decidir um dia inteiro custa um `strptime`, sem abrir arquivo nenhum. Roda em thread
própria na abertura — disco lento não pode atrasar o ícone da bandeja.

Duas barreiras, porque a biblioteca é a pasta do **dono**: só apaga sufixo que o app escreve
(`.json`, `.wav`, `.jsonl`), e só desce em pasta com forma exata de data. Um `.md` seu na mesma
pasta fica; `projeto-importante/` na raiz não é tocado.

### Por quê — as notificações
`--urgency critical` **não expira**, por especificação do freedesktop, e o daemon do Cinnamon ignora
`--expire-time` quando a urgência é crítica. Perde-se o realce e ganha-se a única coisa que importa:
ela sai. A notificação é o **quarto** canal do alarme — a pílula já grita por forma, cor, movimento
e som. Uma que não fecha treina a pessoa a ignorar todas.

### A regra que não foi enfraquecida
O áudio continua sobrevivendo quando **não há texto** para substituí-lo: transcrição que levantou,
nada captado, texto vazio. Sem texto não existe substituição, e aí o `.wav` é a única prova. A
detecção de microfone morto atrasa 50 ms no pior caso e segue dentro de `grace + dead_ms`.

### Como foi verificado
271 testes verdes, `ruff` limpo, catálogo com 0 sem tradução e 0 duvidosa. O vazamento foi
reproduzido com o **motor Whisper de verdade** e o áudio real do dono — `_write_meta('done') ->
True`, `ever_heard = True`, `WAV apagado = True`. Quatro testes novos na varredura (apaga o vencido,
poupa arquivo de terceiro, `0` não apaga nada, ignora pasta que não é data) e um na chave do cofre
(começa desligada e não lembra do ligado anterior).

### Documentação
`docs/armadilhas.md` **1.13**, **8.3** e **9.6**.

---

## 2026-08-16 — o F10 vira "F9 sem segurar", e a nota se nomeia sozinha

### O quê
1. **As duas teclas terminam igual.** O F10 passa pelo cartão de revisão, como o F9: o texto
   aparece, você edita, `⏎` envia, `Tab` descarta. Antes ele ia direto para o disco.
2. **A caixa perguntando o assunto acabou.** `notes.subject_from()` tira o título da primeira
   frase do texto **aprovado** — 8 palavras ou 60 caracteres, sem pontuação nas pontas.
3. **Só o que foi aprovado é publicado.** Descartar no cartão não escreve nota nenhuma; o JSON da
   sessão continua no disco de qualquer jeito.
4. O F10 **continua transcrevendo em pedaços** enquanto você fala. Isso não mudou, e é o que
   permite gravar uma hora sem esperar ~25 minutos de transcrição no fim.

### Por quê
Decisão do dono: o F10 devia ser o F9 sem precisar segurar, não um modo separado com regras
próprias. Duas formas de terminar a mesma gravação era complexidade sem motivo.

E o modal do assunto era a pergunta errada na hora errada: ninguém escreve nada ali, aperta Enter,
e o cofre enche de `reuniao-0710`, `reuniao-1432` — nomes que ninguém acha depois. O objetivo do
nome é ser encontrado, e ele falhava exatamente nisso. Agora
`Alinhamento do orçamento de agosto. Depois falamos do resto.` vira
`2026-08-16-alinhamento-do-orcamento-de-agosto.md`.

### A regra que não foi enfraquecida
Uma gravação longa **nunca** é colada sem ser vista. Com a confirmação desligada, o F10 salva e não
cola: despejar uma hora de transcrição no campo que estiver em foco é uma pequena catástrofe, e sem
o cartão ninguém olhou o texto.

### Como foi verificado
265 testes verdes, `ruff` limpo, catálogo com 0 sem tradução e 0 duvidosa. Quatro testes novos no
`subject_from`: corta na frase, corta por palavra quando não há pontuação, devolve vazio para texto
vazio, e o resultado ainda passa pelo `slugify` virando nome de arquivo válido.

### Documentação
`docs/armadilhas.md` **10.7**.

---

## 2026-08-16 — as gravações mudaram de casa: `~/Documentos/Dito`, por ano/mês/dia

### O quê
1. Uma sessão passa a morar em **`~/Documentos/Dito/2026/08/16/07-42-13.json`**, com o `.wav` e os
   parciais ao lado, mesmo nome. Antes era `~/.local/share/dito/sessions/` num diretório plano.
2. O nome é o **segundo** em que a gravação começou. Duas na mesma segunda (F9 e F10 juntos) ganham
   `-2`, nunca sobrescrevem.
3. A tela de transcrições varre a árvore inteira e lê **as duas raízes** — nada do que já existia
   sai da lista.
4. A data sobrevive a um JSON corrompido: ela é recuperável de `…/2026/08/16` + `07-42-13`.

### Por quê
Pedido do dono: a gravação tem que estar numa pasta comum, em Documentos, para ele — ou qualquer
programa — pegar e usar como contexto sem saber nada do Dito. `~/.local/share` é o lugar certo para
estado de aplicativo e o lugar errado para o produto do trabalho de alguém.

### A barreira que faltava
Ao mover, a suíte escreveu **38 arquivos de teste dentro do `~/Documentos/Dito` real**, ao lado de
uma gravação de verdade. Foi a segunda vez que a suíte tocou nos arquivos do dono (a primeira foi o
`config.toml`, em 7.13). As duas vezes o efeito era invisível para a fixture, porque o caminho é
resolvido a partir do `$HOME` lá no fundo do código.

Agora existe `tests/conftest.py`: `$HOME` e todos os `XDG_*` apontam para um diretório temporário
durante a suíte inteira, e a raiz da biblioteca é fixada por teste. `XAUTHORITY` fica de fora de
propósito — os testes de X11 falam com um servidor X de verdade.

### Como foi verificado
261 testes verdes, `ruff` limpo. Conferido depois de rodar: `~/Documentos/Dito` continua com **1**
arquivo (a gravação real) e o `config.toml` está com o mtime de antes. Prova manual dos dois
formatos convivendo, e de um JSON corrompido ainda mostrando a data certa.

---

## 2026-08-16 — o alarme de uma gravação que nunca começou ficava na tela para sempre

### O quê
`_end()` dispensa o alarme quando não havia sessão para parar — e só quando **nenhuma outra**
está viva. A dispensa espera o alarme completar `TOAST_MS` (1800 ms) na tela.

### Por quê
O `preflight` recusa, emite `AudioAlarm(DEAD)` e o `_begin()` tira a sessão do dicionário: ela
nunca existiu. Ao soltar a tecla, o `_end()` faz `pop`, recebe `None` e **retorna** — não há o que
parar, então ninguém apaga a pílula, e ela fica vermelha até o app reiniciar. O caminho de sucesso
apagava o alarme como efeito colateral de encerrar a gravação; o de recusa não tinha esse efeito.

Um alarme que não sai é tão ruim quanto um que não aparece: na vez seguinte ninguém sabe se o
vermelho é de agora ou de vinte minutos atrás.

O piso de 1800 ms não é enfeite: um toque rápido no F9 sem microfone mostraria o vermelho por
80 ms, que é o mesmo que não mostrar. É o número já medido contra velocidade de leitura.

### A regra que não foi enfraquecida
O alarme **durante** uma gravação continua até a gravação acabar. A dispensa exige que nada esteja
gravando, senão soltar o F9 apagaria o alarme legítimo de um F10 em curso.

### Como foi verificado
260 testes verdes, `ruff` limpo. Dois testes novos: o alarme órfão se apaga, e a mesma chamada num
estado de gravação não faz nada.

### Documentação
`docs/armadilhas.md` **9.5**.

---

## 2026-08-16 — trocar o idioma deixava a tela pela metade

### O quê
`Select.set_options()` restaura a escolha **dentro** do bloqueio de sinais. Se o valor escolhido
não existe mais na lista nova, o sinal é emitido à mão.

### Por quê
Trocar o idioma deixava parte do texto no idioma antigo e a janela parecia travar, só reabrindo.
O `set_value(chosen)` rodava **depois** do `blockSignals(blocked)`, então cada troca de rótulo
disparava `currentIndexChanged` → `on_change` → `_persist()` → `config.save()`. A docstring
prometia "relabelling never changes the setting"; o código não cumpria.

Escrever arquivo dentro de um slot do Qt cobrou o resto: o `save()` chega em `Path.home()`, que faz
`import ntpath` na primeira vez, e esse import cai no gancho do `shibokensupport` com a pilha funda
por causa da emissão — `RecursionError`. A exceção subia do meio do laço de retradução e as telas
seguintes nunca eram retraduzidas.

Efeito colateral que ninguém tinha notado: **a suíte gravava no `~/.config/dito/config.toml` do
dono** a cada execução. Sinal de Qt que escreve disco é sempre suspeito.

### Como foi verificado
258 testes verdes, `ruff` limpo. O teste que reprovava
(`test_switching_the_language_changes_the_text_without_reopening`) passa. Dois testes novos
prendem os dois lados: rótulo trocado **não** anuncia, valor que sumiu **anuncia**. Conferido
também que, com o laço completo, sobram **0** textos em inglês depois de trocar para pt-BR. A
suíte caiu de 35 s para 20 s — era o custo da gravação em disco a cada retradução.

### E mais: o botão do alarme saía escrito "orrigir"

`Size.HUD_W` era aplicado como `setFixedWidth`, e a linha do topo da pílula tem cinco itens sem
esticamento. Medido em português: os itens pedem 330 px e há 308 — faltando 22 e sem ninguém
elástico, o Qt encolhe **todos**, inclusive o botão, cuja política é `Fixed`. Os 82 px de
`sizeHint` viravam 69 na tela, e a diferença come a primeira letra. `Fix` tem 3 letras,
`Corrigir` tem 8: a largura foi escolhida olhando a palavra inglesa.

O `_nudge()` já prometia na docstring *"the pill grows from where it is"*, e a linha seguinte
jogava a medição fora. Agora `HUD_W` é **piso**: `max(HUD_W, o que a linha precisa)`. A medida sai
do layout da linha e não do widget inteiro, porque o `_detail` quebra linha e o `sizeHint` de um
`QLabel` que quebra é a frase inteira **sem** quebrar — esticaria a pílula até a tela.

Medido depois: `Fix` → 378 px, `Corrigir` → 400 px, nenhum cortando. Ver `docs/armadilhas.md`
**7.14**.

### Documentação
`docs/armadilhas.md` **7.13** e **7.14**.

---

## 2026-08-16 — o pacote instalava sem ícone na bandeja

### O quê
1. **`qt6-svg-plugins` entrou no `Depends`** do `.deb`.
2. **O carregamento de ícone pergunta ao ícone, não ao sistema de arquivos.** `_loaded()` devolve
   `None` quando o `QIcon` sai nulo, e a cadeia virou SVG → PNG → desenhado. Os PNGs de 22 e 44 px
   dos três estados já iam dentro do pacote, sem uso.
3. `assets_present()` removido — não tinha nenhum chamador.
4. **Espaço abaixo das abas:** `QTabWidget::pane` ganhou `padding-top`. Sem borda e sem espaçamento,
   o conteúdo ficava colado na aba.
5. **`Engine.backend` traduz na leitura.** Guardava `"não carregado"` em português cravado, escrito
   no construtor — errado duas vezes: fora do catálogo, e congelado no idioma do momento num app que
   troca idioma sem reiniciar.

### Por quê
Instalação limpa, app no ar, `QSystemTrayIcon::setVisible: No Icon set` no log e **nenhum ícone na
bandeja** — que é a única porta de entrada do app (garantia nº 4). O `Depends` trazia as ligações
Python do QtSvg e a biblioteca, mas não o plugin de formato de imagem. Medido: o Qt do pacote lista
13 formatos e **svg não está entre eles**; o Qt do venv do projeto lista svg. Foi por isso que
passou em toda a suíte — ela roda onde o PySide6 vem do pip, que traz o plugin junto.

O segundo erro é o que transformou uma dependência faltando em tela vazia: o código perguntava
`path.exists()`. O arquivo existe, ele só não renderiza; o `if` era satisfeito e o fallback
desenhado, que existe exatamente para esse caso, nunca era alcançado.

### Como foi verificado
256 testes verdes, `ruff` limpo, catálogo com 0 sem tradução e 0 duvidosa. Teste novo reproduz o
defeito sem depender do plugin: um `.svg` corrompido ao lado dos PNGs válidos, e a asserção de que
o ícone volta não-nulo **e com pixmap** — é o `availableSizes()` que prova que o ramo do PNG rodou.
Outro teste tira todos os arquivos e exige que ainda assim venha ícone.

### Documentação
`docs/armadilhas.md` **6.5**.

---

## 2026-08-16 — o instalador não matava o processo antigo

### O quê
`tools/instalar.sh` passou a escolher os processos a parar por "é um interpretador Python?"
(`*/python*`) em vez de `*dito*python*|/usr/bin/python3`. Ganhou `KILL` para quem ignora o `TERM`
e um aviso quando o socket de controle continua ocupado no fim.

### Por quê
O passo imprimia "Parando o Dito que está rodando" e nenhum `parei o pid`: `/proc/PID/exe` aponta
para o binário final, e o `python3` de um venv é link para o do sistema. Medido aqui — `cmdline`
tem `/home/luis/Desktop/Projetos/dito/.venv/bin/python3 .venv/bin/dito listen`, mas `exe` é
`/usr/bin/python3.13`. O caminho com "dito" está no `cmdline`; o Debian entrega `python3.13`, não
`python3`. Nenhum dos dois padrões casava, então o processo velho sobrevivia à instalação segurando
o socket e a trava de instância única — pacote novo instalado, comportamento velho na tela.

O guarda por executável continua existindo pelo motivo original: `pkill -f "dito listen"` casaria
com o próprio shell do script. Com `*/python*` o shell (`exe=/usr/bin/bash`) segue de fora.

### Como foi verificado
`bash -n` limpo; o novo padrão selecionou o processo real (pid 65200, `exe=/usr/bin/python3.13`) e
ignorou o shell.

### Documentação
`docs/armadilhas.md` **5.8**.

---

## 2026-08-16 — o microfone que a tela oferecia e nunca abria, a roda que editava sozinha

### O quê
1. **A lista de entradas só oferece o que a captura consegue abrir.** `supports_rate()` pergunta
   ao PortAudio se o aparelho aceita 16 kHz; `list_usable_inputs()` filtra. O aparelho fixado que
   **não** abre continua listado, rotulado *"não grava a 16 kHz"*.
2. **O `preflight` recusa com motivo e conserto**, não com `errno` de biblioteca. Sonda **só**
   quando há aparelho fixado — o caminho padrão custa 30 ms e não pode pagar mais 18 por tecla.
3. **A roda do mouse não edita mais o controle por onde passa.** `Select` nunca aceita a roda;
   `Spin` aceita só com foco.
4. **Falha de captura não deixa sessão salva.** O JSON escrito antes de abrir o microfone é
   removido quando o `Capture.start()` levanta.
5. `devices.py` passou pelo `gettext` — tinha três textos em português cravados que escaparam da
   migração de idioma.

### Por quê
F9 respondia *"microfone indisponível: Invalid sample rate"* em toda tentativa, com o microfone
perfeito no resto do sistema. A configuração apontava para `ALC887-VD Alt Analog (hw:1,2)` —
oferecido pela **própria tela do app**. Medido nesta máquina: das 4 entradas listadas, **2 não
abrem a 16 kHz**, e são justamente as com nome de microfone; `pipewire` e `default` parecem opção
genérica e são as únicas que funcionam. O headset USB que o dono usa nem aparece na lista — aqui
ele só existe atrás do PipeWire. Oferecer uma opção impossível é o defeito; o `preflight` passava
porque só perguntava se o aparelho *existe*, e ele existe.

A roda do mouse é a mesma classe de defeito: passa por typecheck, por lint e por leitura do fonte,
e só aparece quando alguém rola a tela e uma configuração muda sozinha.

### A regra que não foi enfraquecida
A recusa continua fechada e barulhenta — o alarme dispara igual, agora com texto que diz o que
fazer. E o JSON removido é de uma sessão que **não tem áudio nem texto**: o `Capture` levantou
antes de o `WavWriter` existir, então não há gravação para perder.

### Como foi verificado
253 testes verdes, `ruff` limpo, catálogo pt-BR com 0 sem tradução e 0 duvidosa. Provas rodadas
nesta máquina: `check_input_settings(16000)` devolve `-9997` nos dois `hw:`; o `preflight` com a
configuração antiga recusa com *"o microfone «…» não grava a 16000 Hz"* + *"escolha «Padrão do
sistema»"*; com a nova, passa; e o `Capture` real entregou **50 blocos em 2,5 s** sem erro.

### Documentação
`docs/armadilhas.md` **1.12** (a lista que oferecia o impossível) e **7.12** (a roda que edita).

---

## 2026-08-16 — interface componentizada, tema ao vivo e inglês como língua-fonte

Registro do que entrou no commit `548aa1c` e não tinha passado por aqui.

### O quê
1. **Conjunto de componentes** (`ui/components.py`): botão, campo, `select`, `switch`, cartão,
   linha de formulário e etiqueta, cada um com os seis estados, todos lendo de `theme.py`. As
   telas usam eles em vez de escrever folha de estilo por widget.
2. **Tema e idioma trocam sem reiniciar**, aplicando nas janelas já abertas.
3. **As strings-fonte são inglês** e o catálogo é `gettext` — idioma virou configuração, não
   recompilação. 214 entradas em pt-BR.
4. A pílula ganhou tokens próprios de controle (`hud_edge`, `hud_field`, `hud_solid_*`).
5. O `selftest` parou de escrever em `sessions/` — é diagnóstico, não gravação, e sete deles
   apareciam na janela como "a recuperar".

### Por quê
Branco com alfa escolhido a olho sobre fundo escuro é o jeito fácil de desenhar um controle
invisível: 0,14 de branco mede **1,51** contra `hud_surface`, metade dos 3,0 que uma borda
operável deve. E configuração que exige reiniciar é configuração que todo mundo acha quebrada.

### Como foi verificado
Um teste percorre todo módulo sob `ui/` e reprova quem escrever cor ou pixel numa tela.

---

## 2026-08-15 — sessão vira um JSON de 238 bytes, e o áudio não fica

### O quê
1. **Uma sessão = um arquivo JSON solto**, com data e modo no nome, sem pasta. Era uma pasta com
   `audio.wav` + `session.json` + `transcript.jsonl`.
2. **O áudio é apagado assim que a transcrição está gravada** — ditado e reunião. Medido: 160 kB
   de WAV durante a fala, **238 bytes** no fim.
3. `audio/encode.py` (Opus) e `library.collect_garbage` **removidos**: sem áudio guardado, não há
   o que comprimir nem o que coletar.
4. Configuração limpa do que não tinha leitor: `retention` inteiro, `meeting.max_hours`,
   `meeting.low_disk_warn_gb`, `ui.overlay_position`, `hotkeys.cancel`.

### Por quê
115 MB/hora não se sustenta — decisão do dono. A rede de segurança continua intacta: o áudio vai
para o disco desde o primeiro bloco, porque é o que sobra se o app morrer no meio.

### A regra que não foi enfraquecida
O WAV só some quando o JSON foi escrito, **relido do disco** e o texto conferido. E **nunca** some
quando a transcrição levantou, quando nada foi captado ou quando o texto saiu vazio — sem texto
não existe substituição, e o áudio é a única prova do que foi dito.

### Compatibilidade
Sessões antigas em formato de pasta continuam listadas, com o áudio delas. Nada as apaga
automaticamente; o total aparece na janela e a decisão é do dono.

### Como foi verificado
188 testes verdes. Provam: áudio some no ditado e na reunião; **fica** quando a transcrição
levanta, quando nada foi captado e quando o texto não conseguiu ser escrito; os parciais da
reunião estão no disco durante a gravação e somem com o JSON final; sessão é arquivo e não cria
pasta; pasta antiga ainda aparece; o JSON nunca é apagado.

## 2026-08-15 — interface, marca, reunião no Obsidian e pacote `.deb`

### O quê

1. **Sistema visual** (`ui/theme.py`) — toda cor, espaço, raio, tamanho e duração saem de um lugar
   só. Cor nomeada por PAPEL, então claro e escuro atravessam **sem um `if`** em nenhum widget.
2. **Movimento com mola de verdade** (`ui/spring.py`) — `QPropertyAnimation` interpola entre dois
   pontos num tempo fixo; re-mirar no meio faz ela reiniciar do que ela achar que era o começo,
   que é o salto visível das interfaces desleixadas. Mola só tem valor atual, velocidade e alvo.
3. **A pílula flutuante** (`ui/overlay.py`) — nunca toma foco (o texto vai para o campo onde você
   estava). O alarme é alto em **três canais independentes**: a onda vira linha reta (forma), a
   pílula enche de vermelho (cor) e ela treme uma vez (movimento, que pega visão periférica).
4. **Bandeja, janela e captura de tecla** — nada abre no login; a janela vem do menu ou da
   bandeja, e uma segunda execução do binário fala com a que já roda em vez de criar outra.
5. **Reunião completa** — corta em trechos e transcreve durante, salva texto + Opus em
   `~/Documentos/Dito` e escreve a nota no cofre no formato da skill `reuniao`.
6. **Marca própria** — balão de fala com a onda dentro, e três ícones de bandeja.
7. **Pacote `.deb`** de 111 KB, publicável no `apt.defaltm.com`.

### Decisões de projeto que valem registro

- **`pip install` no `postinst` está fora.** Como root, escreve fora do controle do dpkg, contraria
  a política do Debian, e um `postinst` que falha trava o apt sem nenhuma janela para explicar.
  O bootstrap roda na primeira execução, como usuário, com barra e botão de tentar de novo. E não
  é exigência nova: o app já precisa baixar o modelo de 464 MB no primeiro uso.
- **O `.deb` tem que ser fino** — o Cloudflare Pages, onde o `apt.defaltm.com` mora, **não serve
  arquivo acima de 25 MiB**. Não é preferência, é a hospedagem.
- **Reunião não cola.** Ditado cola onde o cursor está; despejar uma hora de transcrição no campo
  em foco seria uma pequena catástrofe.
- **O Dito não resume.** A nota sai com a transcrição e as seções prontas para preencher.
- **O áudio não entra no cofre por padrão** — é repo git com auto-commit.
- **Reunião não tem limite de tempo** (`max_horas = 0`). No lugar de um teto existe aviso de disco
  cheio, que avisa e nunca interrompe.

### Como foi verificado

**140 testes verdes**, `ruff` limpo. Os que provam algo que não daria para afirmar de outro jeito:

- Contraste **por papel** nos dois temas (4.5 conteúdo, 3.0 dica e contorno de controle).
- O alarme desenha uma **forma diferente**, medido renderizando os dois estados fora da tela.
- Os três ícones de bandeja se distinguem **só pela silhueta a 22 px** (idle×recording 22,5%,
  idle×alert 49,6%, recording×alert 36,2%).
- O chunker empurrando **3 horas** de fala contínua nunca segura mais que 45 s de áudio, e todo
  sample que entra sai exatamente uma vez.
- Cofre inexistente não é criado e a reunião não se perde; biblioteca sem permissão de escrita cai
  na pasta da sessão; assunto `../../etc/passwd` não escapa da pasta.
- Opus medido: WAV 5,7 MB → 519 kB; 3 h ≈ 31 MB. O WAV só é apagado depois de o Opus ser
  **decodificado de volta** e conferido.

### Defeitos encontrados pela própria verificação, antes de sair

- **A trava de instância única do código antigo nunca funcionou.** `voice_type.py:1120` chamava
  `claim_single_instance()` e **descartava o retorno**, então o CPython fechava o socket na hora.
  Provado: o Dito tomou a mesma trava com o ditado antigo rodando, e `ss -x -l` não mostrava o
  nome. Dois ditados sempre puderam rodar juntos colando tudo em dobro.
- **No tema escuro, branco sobre o `danger` media 2,77** — ilegível, no único estado que justifica
  o produto existir. A pílula agora tem superfície própria, igual nos dois temas, medida em 5,18.
- O contorno de controle media 1,95 contra os 3,0 que a WCAG 1.4.11 pede; o cartão media 1,079
  contra a página e não lia como outro plano.
- O `QScrollArea` não herda o fundo da janela e pintava **faixas brancas** entre os cartões.
- Um teste falhava pelo motivo errado: o XTest injeta no servidor X, não num processo, então duas
  execuções simultâneas apertam as teclas uma da outra. Agora há trava entre processos.

### Corrigido no meio do caminho, por medição

Um teste meu estava errado, não o código: âmbar e vermelho diferem **0,19** em razão de contraste,
o que não prova nada — razão de contraste mede só luminância, e matiz não pontua. O teste passou a
medir matiz, e a garantia não-colorida é a onda virando linha reta.

## 2026-08-15 — ditado de ponta a ponta sem interface, com atalho configurável

### O quê

1. **`platform/linux_x11/hotkeys.py`** — segurar-para-falar e alternar-para-reunião.
2. **`core/session.py`** — uma gravação inteira: pré-checagem → captura → disco → alarme →
   transcrição → texto. Ditado transcreve uma vez no fim (beam 5, precisão); reunião corta em
   trechos e transcreve durante (beam 1, sem limite de tempo).
3. **`core/events.py`** — eventos tipados no lugar de tuplas `("preview", str)`.
4. **`output/paste.py`** — clipboard + Ctrl+V com os três tempos que importam.
5. **`dito listen`** — ditado funcionando **sem interface nenhuma**.

### Decisões de projeto que valem registro

- **Disco antes de tudo.** No consumidor de áudio, a primeira coisa que acontece com cada bloco é
  ser escrito. Só depois vêm nível, alarme e transcrição. É o que garante que modelo que não
  carrega, colagem que falha ou processo morto não custem a fala.
- **Contrapressão sem descartar áudio.** Se a transcrição atrasa, o trecho espera na fila e a
  gravação continua. Descartar trecho para acompanhar perderia fala — a única coisa proibida.
- **`transcript.jsonl` cresce durante a reunião.** Morrer no minuto 50 preserva 0–49 em ordem.
- **A tecla de reunião não para no release.** Ela para na **próxima batida** — reunião não tem
  limite de tempo, foi pedido explícito.
- **Colar que falha devolve resultado, não exceção.** Antes, `paste()` estourando (falta de
  `xclip`) perdia o texto e deixava uma linha num log que ninguém lê.

### Como foi verificado

- **Atalhos, contra um servidor X de verdade, com teclas injetadas por XTest:** segurar 1,5 s
  dura 1,81 s (1,5 + 0,30 de carência); toque de 0,15 s dura 0,46 s; o toggle **ignora o release**;
  gerente pausado fica mudo. 29 testes verdes.
- **Cadeia completa headless:** `dito listen --key f7` + F7 sintético segurado por 2 s →
  gravação, transcrição, `session.json` com `state: done` e `audio.wav` com 32000 frames / 2,00 s
  legível por `wave.open()`.
- **Motor:** carga do modelo em 1,07 s do cache, fallback GPU→CPU disparando como projetado,
  **RTF 0,41 com beam=5** (áudio sintético, VAD desligado).

### O que ainda NÃO foi provado

Palavras de verdade saindo certas. A máquina não tem sintetizador de voz, então o último elo
depende de uma voz humana. Tudo antes dele está provado; isso não.

## 2026-08-15 — projeto próprio, e o alarme de microfone mudo funcionando

Primeiro corte do refactor. O ditado sai de um arquivo único de 1136 linhas dentro do repo `dev` e
passa a ser projeto com casa própria.

### O quê

1. **Base do projeto**: pacote `dito` em `src/`, `pyproject.toml`, venv com
   `--system-site-packages` (reaproveita Qt/numpy/onnxruntime do apt em vez de baixar ~250 MB).
2. **`paths.py`** — todo caminho decidido num lugar só, com fallback XDG de verdade. As variáveis
   `XDG_*` nesta máquina estão **definidas e vazias**, e `os.environ.get(var, padrao)` devolveria
   `""` nesse caso: `Path("") / "dito"` é caminho **relativo**, criado dentro do diretório de
   trabalho de quem chamou. `_xdg` trata vazio como ausente.
3. **`config.py`** — dataclasses tipadas ↔ TOML em `~/.config/dito/config.toml`. Escrita atômica
   (`os.replace`), chave desconhecida preservada em vez de apagada, `schema` versionado, e
   configuração ilegível não impede o app de subir (vira `.toml.broken` e os padrões valem).
4. **`audio/level.py` — o alarme.** Watchdog puro, sem thread e sem relógio próprio.
5. **`audio/writer.py`** — WAV escrito desde o primeiro bloco.
6. **`audio/capture.py`** — stream do PortAudio que **lê a flag `status`** (a versão anterior a
   descartava, e todo overflow sumia).
7. **`dito doctor`** e **`dito selftest`** — diagnóstico e prova do alarme.
8. **`platform/linux_x11/audio_system.py`** — mute e volume por `pactl`, sem levantar exceção.

### Por quê

A versão anterior perdeu 99 segundos de fala em silêncio (`pico=0.0000 rms=0.0000`) e só avisou
depois de soltar a tecla. A causa raiz **não é** tratamento de erro faltando: o PortAudio não
levanta exceção quando a captura morre, ele entrega zeros. Não existe exceção para capturar — só o
nível do sinal denuncia. Por isso o watchdog não é um extra, é o motivo do projeto.

### Decisões de projeto que valem registro

- **Dois alarmes, não um.** `DEAD` (silêncio digital, peak < 1e-4) fica **sempre armado**: zeros
  depois de fala real significam dispositivo que morreu no meio da frase. `QUIET` (peak < 8e-3) só
  vale **enquanto nunca chegou som** — depois disso, silêncio é pausa, e avisar seria mentira.
- **O `wave` da stdlib foi descartado de propósito.** Ele só grava os tamanhos no cabeçalho no
  `close()`: um `kill -9` no meio deixa o arquivo declarando **zero frames** e nenhum player abre —
  os bytes estão lá e nada os lê. O cabeçalho de 44 bytes é escrito na mão e os dois campos de
  tamanho são corrigidos a cada flush, então o arquivo é válido **a qualquer instante**.
- **`pactl` dá a mensagem certa; o nível dá a verdade.** O fone declara `HW_MUTE_CTRL`, então o
  mute pelo sistema é detectável e o botão "Desmutar" resolve. Mas fone sem fio pode mutar no
  dongle com o servidor ainda reportando `Mute: no` — que é justamente o caso que queimou. Os dois
  detectores existem; nenhum sozinho basta.

### Como foi verificado

- `pytest`: **16 testes verdes**, sem hardware — o relógio é injetado, então os limiares são
  testáveis sem dormir e sem microfone.
- `dito selftest --source zeros`: alarme **SEM ÁUDIO em 1,03 s** (carência de 300 ms + janela de
  700 ms). Antes: 99 s sem aviso nenhum.
- `dito selftest --source mic`: WAV de 4,00 s gravado; `wave.open()` confirma 64000 frames,
  1 canal, 16 bits — arquivo íntegro **mesmo no caso em que nada foi captado**.
- `dito doctor`: lista as 5 entradas, resolve o `default`, lê mute (`não`) e volume (`100%`) por
  `pactl` e encontra o modelo `small` no cache do HuggingFace.

### Corrigido durante a verificação

O limiar de "muito baixo" nasceu em 4e-3 e o teste com microfone real mostrou o piso de ruído do
H510 numa sala em silêncio em **0,0038** — colado no limiar. Duas correções guiadas pela medição:
o limiar subiu para **8e-3** (acima do piso, ainda 4,5× abaixo da fala mais fraca já registrada,
0,036) e o alarme âmbar passou a ser **condicionado a nunca ter chegado som**. Sem isso, pausar
2,5 s no meio de um ditado acusaria "áudio muito baixo" — falso positivo puro. Travado em
`test_pause_after_speech_does_not_warn`.
