# Marca

A identidade do Dito. Tudo aqui é derivado de duas coisas: o que o produto precisa dizer, e o que
sobrevive a 22 px num painel que pode ser claro ou escuro. Nenhum número foi escolhido no olho —
cada um está medido mais abaixo, e o comando que mede está no fim do arquivo.

**As cores não moram aqui.** Elas moram em [`src/dito/ui/theme.py`](../src/dito/ui/theme.py), que é a
fonte única. Este documento explica os *papéis* e registra o contraste medido; se um valor divergir,
o `theme.py` está certo — ele é o que roda.

---

## 1. O que a marca precisa dizer

O Dito existe porque a versão anterior gravou 99 segundos de fala com o microfone mudo e não avisou.
A frase que resume o produto é: **é um app que fala quando não está te ouvindo.**

Daí saem três exigências de identidade, nessa ordem de prioridade:

1. **O estado tem que ser legível antes de ser bonito.** O ícone da bandeja é a interface principal
   — na maior parte do tempo é a única coisa visível do Dito.
2. **O alarme tem que quebrar o padrão.** Se o estado de erro parecesse com o estado normal, a marca
   estaria repetindo o bug que o projeto existe para corrigir.
3. **"Dito" é particípio de dizer** — o que foi dito. A marca é sobre fala capturada, não sobre
   equipamento de áudio.

---

## 2. O glifo

### Por que não é um microfone

Microfone é o clichê da categoria: diz "gravação de áudio", que é meio-caminho, e diz respeito ao
*equipamento*, que é justamente a peça que falhou na história deste projeto. Um microfone desenhado
não sabe dizer se está captando — e essa distinção é o produto inteiro.

### O que é

**Um balão de fala cujo corpo é um "D": lado esquerdo reto (a haste), lado direito uma semicircun-
ferência exata (a pança), e a cauda saindo do canto inferior esquerdo.** Dentro dele, um medidor de
nível de três barras.

Três motivos:

- **Balão de fala** = o que foi dito. É a categoria certa (fala), não a categoria do equipamento.
- **A forma de D** dá inicial sem virar charada: a maioria dos balões é retângulo arredondado ou
  elipse; um com aresta esquerda reta e pança semicircular é reconhecível e é a letra da marca.
- **O medidor de nível** é a alma técnica do produto. O nível do sinal é o *único* detector
  confiável de microfone mudo (ver `docs/armadilhas.md`, item 1.1) — é o que `audio/level.py` faz, e
  é o que a marca mostra.

### A regra semântica que rege tudo

> **O medidor só aparece quando existe nível para mostrar.**

Parado, o balão é vazio. Gravando, o medidor acende. Sem captação, o balão desaparece. Não é
decoração: é o mesmo contrato do produto, desenhado.

### Geometria

Um só desenho, numa **grade de 24**, usado em todos os arquivos apenas com escala diferente. A caixa
de tinta do glifo mede exatamente **19,5 × 19,5**, centrada em (12, 12) — é o que torna o
posicionamento trivial em qualquer canvas.

```
balão      M 6.5 3.5 H 15 A 5.5 5.5 0 0 1 15 14.5 H 8.5 L 3.5 20.5 V 6.5 A 3 3 0 0 1 6.5 3.5 Z
triângulo  M 12 3.4 L 20.9 19.8 H 3.1 Z
traço      2,5 · stroke-linejoin="round" · stroke-linecap="round"
```

O contorno é sempre a **linha de centro** somada a um traço de 2,5 (`fill` + `stroke` na mesma cor).
Isso dá canto arredondado de graça e, principalmente, deixa a silhueta externa igual entre a versão
vazada e a cheia — a mesma `d`, dois acabamentos.

**Medidor grande** (`icon.svg`, `logo.svg`) — corpo sólido, sobra espaço:

| barra | x | y | largura | altura | rx |
|---|---|---|---|---|---|
| 1 | 7,15 | 6,5 | 2,5 | 5,0 | 1,25 |
| 2 | 11,15 | 4,5 | 2,5 | 9,0 | 1,25 |
| 3 | 15,15 | 5,7 | 2,5 | 6,6 | 1,25 |

Centros em 8,4 / 12,4 / 16,4 — deslocados 0,4 à direita do centro geométrico, porque a lateral
esquerda é reta e a direita é curva: opticamente o vão da direita parece maior.

**Medidor de bandeja** (`tray-recording.svg`) — **redesenhado para 22 px, não reduzido**:

| barra | x | y | largura | altura | rx |
|---|---|---|---|---|---|
| 1 | 6,7 | 7,2 | 2,2 | 3,6 | 1,1 |
| 2 | 10,9 | 5,5 | 2,2 | 7,0 | 1,1 |
| 3 | 15,1 | 6,5 | 2,2 | 5,0 | 1,1 |

Mais estreitas, mais baixas e mais espalhadas (centros em 8 / 12 / 16, sem o deslocamento óptico).
A 22 px uma barra tem ~2 px, e o que faz três barras lerem como três é o **vão** entre elas, não a
grossura: a largura foi trocada por separação. O deslocamento óptico de 0,4 vale 0,37 px nesse
tamanho — não se enxerga, e custa folga na borda direita.

---

## 3. Os três estados da bandeja

| arquivo | forma | núcleo | o que diz |
|---|---|---|---|
| `tray-idle.svg` | balão **vazado** | `text_muted` `#6b6b7a` | estou aqui, calado |
| `tray-recording.svg` | balão **cheio** + medidor | `primary` `#4b3bd4` | estou te ouvindo |
| `tray-alert.svg` | **triângulo** + exclamação | `danger` `#c62a30` | **não estou te ouvindo** |

### Duas decisões que valem mais que o desenho

**1. Gravando é índigo, não vermelho.** Vermelho é a convenção do "REC", mas neste produto ele tem
trabalho mais importante: se o estado normal também fosse vermelho, vermelho no painel deixaria de
significar alguma coisa. Aqui **vermelho no painel quer dizer exatamente uma coisa: parou de te
ouvir.** Gravar é o app fazendo o trabalho dele, e o papel disso na paleta é `primary`.

**2. No alarme o balão some.** É a decisão mais importante do conjunto. O Dito é um balão enquanto
está te ouvindo; quando não está, o balão vira a única forma que qualquer pessoa lê como problema.
Redondo × triangular sobrevive a 22 px, a desfoque e a daltonismo — ponto vermelho ao lado de balão
vermelho, não.

### Como cada ícone funciona em painel claro **e** escuro

Cada ícone tem **dois tons**: um núcleo colorido e um contorno de guarda (*keyline*) em
`hud_text` `#f7f7f9`. O núcleo carrega o ícone no painel claro; a keyline carrega no escuro.

Isso não é enfeite, é a consequência de uma medição: **nenhuma cor chapada da paleta atinge 3:1 nos
dois tipos de painel** (a melhor é 2,41). Nem uma cor chapada ideal atingiria muito mais — o teto
teórico para um cinza qualquer entre `#dcdce3` e `#2e3436` é 3,06. Duas camadas resolvem o que uma
camada não resolve.

Nos ícones cheios a keyline é pintada primeiro (`fill` + `stroke` 2,5) e o núcleo por cima
(só `fill`): o anel claro fica **por dentro** da silhueta, então o ícone não muda de tamanho entre
os estados. No vazado, a keyline é um traço de 3,4 por baixo de um traço de 2,0.

---

## 4. Paleta

Os valores estão em `theme.py`. Aqui ficam os **papéis** e onde cada um aparece na marca.

### Papéis semânticos (tríade `default` / `hover` / `active`)

| papel | claro | escuro | na marca |
|---|---|---|---|
| `primary` | `#4b3bd4` · `#3f31b8` · `#342899` | `#8b7cff` · `#9c90ff` · `#7a6af0` | placa do ícone, glifo do logo, bandeja gravando |
| `danger` | `#c62a30` · `#ab2126` · `#8f1a1e` | `#ff6b6f` · `#ff8285` · `#e85054` | bandeja alarme |
| `success` | `#1f7a4d` | `#4ecf8f` | — |
| `alert` | `#8a5a06` | `#f0b95c` | — (reservado para "áudio muito baixo") |

A tríade não é gradação decorativa: é a mesma cor um degrau e dois degraus mais escura, decidida uma
vez. **O gradiente da placa do ícone usa exatamente `primary` → `primary_active`** — o ponto médio
desse gradiente cai em `#3f31b6`, a dois pontos de azul do `primary_hover` `#3f31b8`, que por isso é
a cor das barras vazadas. A escala fecha sozinha; não há cor inventada no ícone.

### Neutros, nomeados pelo papel

| papel | claro | escuro |
|---|---|---|
| `bg` | `#f6f6f8` | `#111116` |
| `surface` · `surface_alt` | `#ffffff` · `#eeeef2` | `#1b1b21` · `#25252e` |
| `border` · `border_strong` | `#dcdce3` · `#b9b9c4` | `#33333e` · `#4c4c5a` |
| `text_primary` · `secondary` · `muted` | `#16161a` · `#43434e` · `#6b6b7a` | `#f5f5f7` · `#c2c2cd` · `#8e8e9d` |

### A pílula flutuante (HUD)

`hud_surface #17171c` · `hud_text #f7f7f9` · `hud_muted #a3a3b2` — **escura nos dois temas**, porque
ela flutua sobre conteúdo arbitrário e uma pílula clara sumiria dentro de uma janela clara.

> ⚠️ **Consequência que precisa estar escrita:** a pílula é escura sempre, então o que for pintado
> sobre ela tem que usar os valores do tema **escuro**, mesmo com o app no tema claro.
> `danger` claro `#c62a30` sobre `hud_surface` mede **3,21** (abaixo do piso 4,5 de conteúdo);
> `danger` escuro `#ff6b6f` sobre a mesma superfície mede **6,45**. Vale para todo papel semântico
> que aparecer na pílula — e o alarme aparece justamente ali.

---

## 5. Contraste medido

Medido com `theme.contrast()` (WCAG 2.x), com o piso **por papel** da tabela `CONTRAST_FLOOR` do
`theme.py` — "4,5 para tudo" reprova decisão correta (dica com contraste de conteúdo deixa de ler
como dica; borda de cartão não é controle).

### A marca

| par | medido | piso | |
|---|---|---|---|
| glifo branco `#f7f7f9` / topo do gradiente `#4b3bd4` | **6,83** | 4,5 | ✅ |
| glifo branco / base do gradiente `#342899` | **10,28** | 4,5 | ✅ |
| barras `#3f31b8` / glifo branco | **8,38** | 3,0 | ✅ |
| glifo índigo `#4b3bd4` / papel branco | **7,30** | 3,0 | ✅ |
| glifo índigo / `bg #f6f6f8` | **6,77** | 3,0 | ✅ |
| barras brancas / glifo índigo | **7,30** | 3,0 | ✅ |
| wordmark `#16161a` / papel branco | **18,04** | 4,5 | ✅ |
| wordmark / `bg #f6f6f8` | **16,72** | 4,5 | ✅ |

### A bandeja, nos quatro painéis que existem na prática

Para um ícone de dois tons vale **o maior dos dois** — é o tom que está sendo enxergado.

| estado | `#f6f6f8` claro | `#dcdce3` claro alt | `#2e3436` escuro | `#17171c` preto |
|---|---|---|---|---|
| `tray-idle` | **4,85** núcleo | **3,84** núcleo | **11,82** keyline | **16,69** keyline |
| `tray-recording` | **6,77** núcleo | **5,35** núcleo | **11,82** keyline | **16,69** keyline |
| `tray-alert` | **5,15** núcleo | **4,08** núcleo | **11,82** keyline | **16,69** keyline |

Pior caso do conjunto: **3,84**, acima do piso 3,0 de contorno de controle (WCAG 1.4.11). Tom a tom,
para mostrar por que uma camada só não bastaria:

| tom | `#f6f6f8` | `#dcdce3` | `#2e3436` | `#17171c` |
|---|---|---|---|---|
| núcleo idle `#6b6b7a` | 4,85 | 3,84 | 2,41 ❌ | 3,41 |
| núcleo gravando `#4b3bd4` | 6,77 | 5,35 | 1,73 ❌ | 2,45 ❌ |
| núcleo alarme `#c62a30` | 5,15 | 4,08 | 2,27 ❌ | 3,21 |
| keyline `#f7f7f9` | 1,01 ❌ | 1,28 ❌ | 11,82 | 16,69 |

### A interface

| par | claro | escuro | piso |
|---|---|---|---|
| `text_primary` / `bg` | 15,85 | 17,68 | 4,5 |
| `text_secondary` / `bg` | 8,58 | 10,90 | 4,5 |
| `text_muted` / `surface` (dica) | 5,24 | 5,31 | 3,0 |
| `text_inverse` / `primary` (rótulo em botão cheio) | 7,30 | 5,52 | 4,5 |
| `text_inverse` / `danger` | 5,56 | 6,52 | 4,5 |
| `primary` / `bg` (link, anel de foco) | 6,42 | 5,89 | 3,0 |
| `danger` / `bg` | 4,89 | 6,95 | 4,5 |
| `success` / `bg` | 4,67 | 9,76 | 4,5 |
| `alert` / `bg` | 5,20 | 10,82 | 4,5 |
| `border_strong` / `surface` (contorno de controle) | 3,20 | 3,30 | 3,0 |
| `border` / `surface` (divisória) | 1,36 | 1,37 | 1,1 |
| `surface` / `bg` (cartão na página) | 1,14 | 1,12 | 1,1 |
| `hud_text` / `hud_surface` | 16,69 | 16,69 | 4,5 |
| `hud_muted` / `hud_surface` | 7,18 | 7,18 | 3,0 |

Tudo passa. A única exceção é a do aviso da seção 4: papel semântico **do tema claro** sobre a
pílula escura.

---

## 6. Tipografia

**Não existe Inter nesta máquina** — conferido com `fc-list : family | grep -ix inter` (vazio) e com
`fc-match Inter`, que cai em Noto Sans. A pilha é o que existe de verdade:

```
interface   Cantarell, 'Noto Sans', 'DejaVu Sans', sans-serif
número/ID   'DejaVu Sans Mono', monospace
```

Cantarell é a fonte do GNOME, está instalada como variável
(`/usr/share/fonts/opentype/cantarell/Cantarell-VF.otf`, altura de maiúscula 0,694 em) e é a que faz
o app parecer parte do desktop em vez de visita.

| papel | tamanho | peso | entrelinha | tracking |
|---|---|---|---|---|
| `DISPLAY` | 22 | 600 | 1,15 | −0,4 px |
| `TITLE` | 16 | 600 | 1,15 | 0 |
| `BODY` | 13 | 400/500 | 1,5 | 0 |
| `CAPTION` | 11 | 400 | 1,5 | 0 |

Quatro tamanhos resolvem o app. Hierarquia sai de **peso e cor**, não de inventar o quinto tamanho.
Tracking é específico do tamanho: texto grande lê frouxo à medida que cresce, texto pequeno lê
apertado — um `letter-spacing` fixo estaria errado em algum lugar.

### O wordmark

"Dito" em **Cantarell Bold (peso 700), tracking −0,02 em**, convertido para contornos. Nenhuma
referência a fonte sobra no arquivo: o `logo.svg` renderiza igual numa máquina sem Cantarell
instalada. Cantarell é OFL; contorno convertido é desenho, não redistribuição de fonte.

**Não re-digite o wordmark.** Se precisar mexer, mexa na geometria do `logo.svg`. Digitar de novo com
"a fonte parecida" produz um segundo wordmark que ninguém consegue dizer qual é o certo.

---

## 7. Os arquivos

| arquivo | viewBox | o que é |
|---|---|---|
| `icon.svg` | `0 0 256 256` | ícone do app: placa + glifo branco |
| `logo.svg` | `0 -109 449.5 150.5` | assinatura: glifo + "Dito" |
| `tray-idle.svg` | `0 0 24 24` | bandeja, parado |
| `tray-recording.svg` | `0 0 24 24` | bandeja, gravando |
| `tray-alert.svg` | `0 0 24 24` | bandeja, alarme |

### `icon.svg`

Placa de 256 com raio **56** (0,22 do lado — a proporção de ícone de desktop atual), preenchida com
gradiente vertical `primary` → `primary_active`. O glifo entra por `translate(32 32) scale(8)`: a
caixa de 19,5 vira 156, exatamente centrada, ocupando **61 %** da placa.

### `logo.svg`

Deitado sobre a altura de maiúscula (`cap`), que vale **100** unidades no arquivo:

- glifo com **1,5 cap** de altura;
- **0,42 cap** de ar entre glifo e palavra;
- glifo ancorado na faixa de maiúsculas por uma mistura 70/30 entre o centro do **corpo** e o centro
  da **caixa toda** — pelo centro da caixa ele parece alto demais, porque a cauda é fina e não pesa;
- `viewBox` **colado na tinta**, medido no raster: quem usa o arquivo controla o respiro, em vez de
  herdar um respiro embutido aqui.

Proporção resultante: **2,99 : 1**.

O logo é a versão **positiva** (fundo claro). A negativa é o mesmo arquivo com três valores trocados:

| | positivo | negativo |
|---|---|---|
| glifo | `#4b3bd4` | `#8b7cff` |
| barras do medidor | `#ffffff` | `#111116` |
| wordmark | `#16161a` | `#f5f5f7` |

---

## 8. Regras de uso

### Tamanho mínimo

| ativo | mínimo | por quê |
|---|---|---|
| ícones de bandeja | **22 px** | é o tamanho para o qual foram desenhados; é `theme.Size.TRAY_ICON` |
| `icon.svg` | **48 px** | abaixo disso as barras do medidor fecham |
| `logo.svg` | **28 px de altura** | medido: a 24 px as barras começam a se juntar, a 20 px fundem |

Abaixo de 28 px de altura, use o glifo sozinho — nunca a assinatura espremida.

### Área de respiro

**Uma altura de maiúscula (o "D") em volta de tudo**, nos quatro lados — 100 unidades no `logo.svg`,
0,66 da altura total. A regra é derivada, não gosto: o respiro externo tem que ser maior que o maior
vão interno (0,42 cap entre glifo e palavra), senão o que está fora aperta mais que o que está
dentro.

### O que não fazer

- **Não** re-digitar o wordmark, nem trocar a fonte dele.
- **Não** recolorir com valor fora do `theme.py`. Cor nova entra quando existe **papel** novo.
- **Não** ampliar os ícones de bandeja para usar como ícone de app: eles são desenhados para 22 px e
  a keyline vira um anel gordo em tamanho grande. Para tamanho grande existe o `icon.svg`.
- **Não** usar o alarme como decoração, em nenhum lugar. Triângulo vermelho no Dito significa uma
  coisa só; gastá-lo em outro contexto estraga o único aviso que o produto tem.
- **Não** girar, inclinar, aplicar sombra, brilho ou contorno extra.
- **Não** pôr o glifo livre sobre foto ou fundo de cor arbitrária — nesse caso use a placa
  (`icon.svg`), que carrega o próprio fundo.
- **Não** deixar o balão vazio "cheio" nem o cheio "vazio": o medidor só acende quando existe nível.

---

## 9. Restrições técnicas, medidas nesta máquina

Não são preferências. Cada uma foi verificada antes de o desenho depender dela.

- **A rasterização é do QtSvg.** Não há `inkscape`, `imagemagick` nem `rsvg-convert` aqui. Como o Qt
  já é dependência do app, o renderizador que desenha o ícone em produção é o mesmo que assa o PNG.
- **QtSvg ignora `<style>`.** Testado no PySide6 6.8.2.1: com uma regra CSS e um atributo de
  apresentação em conflito, **o atributo vence** e a folha não é aplicada. Ou seja, um
  `@media (prefers-color-scheme: dark)` funcionaria no navegador e silenciosamente não funcionaria no
  app — que é a pior espécie de bug. **Nenhum SVG desta pasta usa CSS**, só atributos.
- **`QSvgRenderer` não tem `setCurrentColor` nesta versão.** `currentColor` é resolvido a partir do
  atributo `color` do arquivo, mas não pode ser trocado em tempo de execução; por isso as cores estão
  escritas nos elementos, uma por arquivo, fáceis de achar com `grep`.
- **Parar em 512.** 1024 não renderiza e já queimou dois projetos desta casa; está registrado no
  `make-deb.sh` padrão e em `docs/armadilhas.md` (6.2).
- **O PNG do Qt é determinístico**: a mesma entrada dá os mesmos bytes, o que é o que permite ao
  `gen_icons.py` ser idempotente por conteúdo e ao `--check` valer alguma coisa.

---

## 10. Gerar os PNG

```bash
.venv/bin/python tools/gen_icons.py            # grava src/dito/ui/assets/png/
.venv/bin/python tools/gen_icons.py --check    # não grava; sai 1 se algum PNG estiver velho
```

Saída atual — 13 arquivos, 45 633 bytes:

| arquivo | dimensão | bytes |
|---|---|---|
| `icon-48.png` … `icon-512.png` | 48, 64, 128, 256, 512 | 1 331 · 1 712 · 3 256 · 6 575 · 14 394 |
| `tray-idle-22/44.png` | 22, 44 | 743 · 1 457 |
| `tray-recording-22/44.png` | 22, 44 | 653 · 1 227 |
| `tray-alert-22/44.png` | 22, 44 | 698 · 1 406 |
| `logo-64/128.png` | 191×64, 382×128 | 4 095 · 8 086 |

Os tamanhos 48/64/128/256/512 são o conjunto hicolor. O 22 é `theme.Size.TRAY_ICON`, e o 44 é o
mesmo em HiDPI — o script lê os dois do `theme.py`, então mudar a constante lá muda o PNG aqui.

---

## 11. A prova de que os três estados se distinguem pela FORMA

Cor sozinha não é acessível, e painel pode ser claro ou escuro. Então a diferença tem que estar na
forma — e isso é medível: renderiza-se cada ícone a 22 px e olha-se **só o canal alfa**, que não sabe
que cor existe.

**Cobertura de tinta** (pixels ao menos meio opacos, de 484):

| ícone | px | cobertura |
|---|---|---|
| `tray-idle` | 155 | 32,0 % |
| `tray-alert` | 180 | 37,2 % |
| `tray-recording` | 222 | 45,9 % |

**Discordância entre pares** (pixels que um tem e o outro não) — é a medida honesta, porque cobertura
parecida ainda pode ser forma diferente:

| par | px | discordância |
|---|---|---|
| idle × gravando | 97 | **20,0 %** |
| gravando × alarme | 170 | **35,1 %** |
| idle × alarme | 207 | **42,8 %** |

Um quinto dos pixels difere no par mais parecido, e quase metade no par que mais importa
(parado × alarme). Nenhuma dessas contas olhou para cor.

---

## 12. O que ficou de fora

- **Não há variante monocromática de uma cor só** (para carimbo, gravação a laser, fax). Se aparecer
  a necessidade, o caminho é o balão vazado sem keyline, em preto.
- **Não há favicon nem Open Graph** — não existe site.
- **O `alert` âmbar não tem ícone próprio.** Hoje "áudio muito baixo" e "sem áudio" compartilham o
  `tray-alert`. Se os dois precisarem se distinguir na bandeja, o desenho previsto é o mesmo
  triângulo com o núcleo em `alert`, e aí a forma passa a não separar os dois — teria que mudar
  também o interior.
- **A animação de pulso do alarme** (`Motion.ALARM_PULSE_MS`, 1000 ms) é da interface, não deste
  documento: aqui só está o desenho parado.
