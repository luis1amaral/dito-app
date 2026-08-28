# Gates — como provar, em vez de "deve funcionar"

Um port tem muita peça que só quebra na máquina do usuário. Estes são os testes que pegam isso
**antes** de publicar. Todos rodam sem interação humana, exceto o último.

Princípio: **exit code é prova, log bonito não é.** Todo gate termina em 0 ou 1.

---

## Gate 1 — o addon compila e exporta o contrato certo

```bash
npx node-gyp configure build --directory=native
node -e "
const a = require('./native/build/Release/dito_linux.node')
const esperado = ['ACTION','startHook','stopHook','hookStatus','rememberTarget',
                  'currentTarget','targetIsForeground','paste','typeText']
const faltando = esperado.filter(k => !(k in a))
if (faltando.length) { console.error('FALTA:', faltando); process.exit(1) }
console.log('contrato completo')
"
```

Pega: erro de compilação, símbolo esquecido, divergência entre a implementação Windows e a Linux.

---

## Gate 2 — a tecla global, sem apertar tecla

`xdotool` injeta por XTest, que **passa pelo `XGrabKey`** igual a uma tecla física. Dá para testar o
hook inteiro sem ninguém na frente do teclado.

```js
const addon = require('.../dito_linux.node')
const edges = []
const ok = addon.startHook('F10', (e) => { if (e.kind === 'edge') edges.push(e) })
console.log('startHook =', ok, JSON.stringify(addon.hookStatus()))

setTimeout(() => {
  const st = addon.hookStatus()
  const downs = edges.filter(e => e.down).length
  const ups   = edges.filter(e => !e.down).length
  console.log(`${downs} down, ${ups} up, seen=${st.seen}, pumps=${st.pumps}`)
  addon.stopHook()
  // 1 toque + 1 segurada = exatamente 2 e 2. Mais que isso e auto-repeat vazando.
  process.exit(downs === 2 && ups === 2 && st.installed ? 0 : 1)
}, 3000)
```

Dispare em paralelo:

```bash
( sleep 1; xdotool key F10; sleep 0.4
  xdotool keydown F10; sleep 0.5; xdotool keyup F10 ) &
DISPLAY=:0 node gate-hook.mjs
```

Pega: grab falhando (`installed:false`), `BadAccess`, auto-repeat vazando, tick parado
(`pumps` não sobe), key-up perdido.

**Foi este gate que encontrou o bug do auto-repeat** — 3 downs para 2 toques.

---

## Gate 3 — a colagem, com clipboard real e arquivo em disco

Não teste o `paste()` isolado: teste a cadeia inteira (clipboard do Electron → atalho por XTest →
app de verdade → bytes no disco). Rode **sob Electron**, não sob node, senão o clipboard não é o
mesmo.

```js
const { app, clipboard } = require('electron')
const TEXT = 'teste com acentuação, ção e ênfase'

app.on('ready', async () => {
  const addon = require('.../dito_linux.node')
  writeFileSync(FILE, '')
  spawn('xed', [FILE], { detached: true, stdio: 'ignore' })
  await sleep(3000)

  const win = xdo('search', '--name', 'dito-gate-paste').split('\n')[0]
  xdo('windowactivate', '--sync', win)
  await sleep(600)

  addon.rememberTarget()
  console.log('ALVO:', JSON.stringify(addon.currentTarget()))

  clipboard.writeText(TEXT)
  await sleep(250)
  console.log('paste() =', addon.paste(TEXT))
  await sleep(800)
  console.log('typeText() =', addon.typeText(' | digitado: ação'))
  await sleep(1500)

  xdo('key', 'ctrl+s')          // SEM --window: XSendEvent e ignorado por app GTK
  await sleep(1500)

  const conteudo = readFileSync(FILE, 'utf8')
  app.exit(conteudo.includes(TEXT) && conteudo.includes('digitado: ação') ? 0 : 1)
})
```

Pega: alvo errado, acento corrompido, atalho errado para o tipo de janela, remapeamento de keysym
que não restaura, clipboard vazio.

O que prova de verdade: **o arquivo em disco**, não o retorno `true` da função. `paste()` retornar
`true` só diz que os eventos foram enfileirados.

---

## Gate 4 — o pacote por dentro, antes de publicar

```bash
npm run pack:linux

# segredo e source map do SEU codigo
dpkg-deb -c dist/*.deb | awk '{print $6}' | grep -Ei '\.map$|\.env|\.pem$|\.key$|secret|token'
npx asar list dist/linux-unpacked/resources/app.asar | grep -E '^/out.*\.map$'

# o nativo saiu do asar?
dpkg-deb -c dist/*.deb | grep -E 'app\.asar\.unpacked.*\.(node|so)'

# o updater vai se reconhecer como deb?
dpkg-deb -c dist/*.deb | grep package-type

# as dependencias resolvem? (simulacao, nao precisa de root)
apt-get -s install ./dist/*.deb

# o que o binario carrega esta declarado?
diff <(ldd dist/linux-unpacked/<app> | grep -oP '(?<= => )/\S+' | xargs -r dpkg -S 2>/dev/null \
        | cut -d: -f1 | sort -u) \
     <(dpkg-deb -f dist/*.deb Depends | tr ',' '\n' | tr -d ' ' | sort -u)
```

O último comando é o que teria pego o `libatspi2.0-0t64` faltando.

---

## Gate 5 — o manifesto bate com os bytes publicados

Depois de subir na release, prove que o feed serve **o pacote que você construiu**:

```python
import base64, hashlib, re
def sha(p):
    return re.search(r'^\s*sha512:\s*(\S+)', open(p).read(), re.M).group(1)
feed  = sha('/tmp/feed.yml')                 # curl do endpoint
local = sha('dist/latest-linux.yml')
calc  = base64.b64encode(hashlib.sha512(open('dist/app.deb','rb').read()).digest()).decode()
assert feed == local == calc
```

Pega: asset trocado pela metade, upload que sobrescreveu um e não o outro, feed com cache velho.

> Cuidado com o parser. Na primeira tentativa eu usei `awk '{print $3}'` num YAML indentado; os dois
> lados vieram **vazios** e a comparação deu "conferem". Um gate que compara vazio com vazio passa
> sempre. **Imprima os valores**, não só o veredicto.

---

## Gate 6 — o app instalado, com voz de verdade

O único que precisa de gente. Não pule: é o que prova o motor de fala, o microfone, a pill e a
colagem juntos.

```bash
sudo apt install ./dist/*.deb
# abrir pelo menu, apertar a tecla, falar uma frase com acento
tail -f ~/.local/state/dito/logs/app.log
```

Procure no log, nesta ordem:

```
key: F10 mode=toggle bound=true installed=true error=0   <- hook
engine: ready in NNNN ms / boot completo                  <- motor carregou
dictation: started                                        <- tecla chegou
transcribed: ... "<a frase que voce falou>"               <- motor entendeu
type: true into gui "<janela alvo>"                       <- colou no lugar certo
updater: checou · feed em X.Y.Z                           <- update funciona
```

Se algum some, o problema está exatamente naquela etapa.

---

## O que cada gate pega, em resumo

| | Gate |
|---|---|
| Compilação, contrato incompleto | 1 |
| Grab, auto-repeat, tick, key-up perdido | 2 |
| Alvo, acento, atalho por tipo de janela, clipboard | 3 |
| Segredo publicado, nativo no asar, dependência faltando | 4 |
| Manifesto divergente do binário | 5 |
| Motor de fala, microfone, cadeia inteira | 6 |

Gates 1–5 rodam sozinhos e cabem no CI. O 6 é o único que precisa de voz humana.
