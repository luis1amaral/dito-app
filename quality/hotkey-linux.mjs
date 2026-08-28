// End-to-end proof that the key starts AND stops a dictation on X11, in the installed app.
// Exists because a 250 ms bounce filter in toggle mode swallowed the second press: the pill went
// away, the app kept recording the room and the desktop audio, and typed it at the ceiling.
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const CONFIG = join(process.env.APPDATA || join(homedir(), '.config'), 'dito', 'config.json')
const STATE = process.env.XDG_STATE_HOME || join(homedir(), '.local', 'state')
const LOG = join(STATE, 'dito', 'logs', 'app.log')
const BUILT = join(import.meta.dirname, '..', 'dist', 'linux-unpacked', 'dito')
// Prove the binary this tree produces; the installed one is the fallback.
const APP = process.argv[2] || (existsSync(BUILT) ? BUILT : '/opt/Dito/dito')
const TARGET_FILE = '/tmp/dito-gate-hotkey.txt'
// The gap that used to be eaten by the bounce filter, and one no filter could ever excuse.
const GAPS_MS = [150, 700]
const SETTLE_MS = 5000

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const sh = (cmd, args) => execFileSync(cmd, args, { encoding: 'utf8' }).trim()

function pending(msg) {
  console.log('HOTKEY: PENDENTE - ' + msg)
  process.exit(2)
}

if (process.platform !== 'linux') pending('este portao e o do X11; no Windows quem prova e hotkey.mjs')
for (const tool of ['xdotool', 'pactl']) {
  try {
    sh('which', [tool])
  } catch {
    pending(`falta ${tool} nesta maquina`)
  }
}
if (!existsSync(APP)) pending(`o app instalado nao esta em ${APP}`)

// Counting by application name is what separates "the app is recording" from any other client.
const capturing = () =>
  execFileSync('pactl', ['list', 'source-outputs'], { encoding: 'utf8' })
    .split(/^Source Output #/m)
    .slice(1)
    .filter((b) => /application\.name = "Dito"/.test(b)).length

// Match on the executable name: -f would also catch the shell that launched this gate.
const running = () => {
  try {
    return sh('pgrep', ['-x', 'dito']).length > 0
  } catch {
    return false
  }
}

const key = existsSync(CONFIG) ? (JSON.parse(readFileSync(CONFIG, 'utf8')).key ?? 'F10') : 'F10'

let started = false
if (!running()) {
  console.log('HOTKEY: subindo o app instalado')
  spawn(APP, ['listen'], { detached: true, stdio: 'ignore' }).unref()
  started = true
  for (let i = 0; i < 60 && !running(); i += 1) await sleep(500)
  await sleep(12000)
}
if (!running()) pending('o app nao subiu')
// A take left running by a previous run (or by the operator) would poison every measurement.
if (capturing() > 0) {
  console.log('HOTKEY: havia captura aberta — mandando parar antes de medir')
  sh('xdotool', ['key', key])
  await sleep(SETTLE_MS)
}
// The settings screen keeps a stream open for the level meter, so the reference is the delta.
const baseline = capturing()
if (baseline > 0) console.log(`HOTKEY: ${baseline} captura(s) ja abertas antes do teste (tela de ajustes?)`)

// Its own target window: whatever the app types at the end must not land on the operator's screen.
writeFileSync(TARGET_FILE, '')
const editor = spawn('xed', [TARGET_FILE], { detached: true, stdio: 'ignore' })
await sleep(3000)
try {
  sh('xdotool', ['windowactivate', '--sync', sh('xdotool', ['search', '--name', 'dito-gate-hotkey']).split('\n')[0]])
  await sleep(500)
} catch {
  console.log('HOTKEY: aviso - nao consegui focar a janela alvo')
}

let failures = 0
for (const gap of GAPS_MS) {
  const mark = existsSync(LOG) ? statSync(LOG).size : 0
  sh('xdotool', ['key', key])
  await sleep(gap)
  sh('xdotool', ['key', key])
  await sleep(SETTLE_MS)

  // Slicing bytes, not characters: the log carries accents and a string offset would drift.
  const tail = existsSync(LOG) ? readFileSync(LOG).subarray(mark).toString('utf8') : ''
  const opened = /dictation: started/.test(tail)
  const closed = /dictation: stopped/.test(tail)
  const left = capturing() - baseline
  console.log(`-- ${key} start, ${String(gap).padStart(3)} ms, ${key} stop · começou ${opened} · parou ${closed} · capturas vivas ${left}`)
  if (!opened) {
    console.log('   REPROVA: a tecla nao iniciou o ditado')
    failures += 1
  }
  if (!closed) {
    console.log('   REPROVA: a segunda tecla nao parou o ditado — o app segue gravando sozinho')
    failures += 1
  }
  if (left > 0) {
    console.log('   REPROVA: sobrou captura viva depois de parar')
    failures += 1
  }
  if (!closed || left > 0) {
    // Never leave the machine recording because of the gate.
    sh('xdotool', ['key', key])
    await sleep(SETTLE_MS)
  }
}

try {
  process.kill(-editor.pid)
} catch {
  /* already gone */
}
if (started) {
  try {
    sh('pkill', ['-x', 'dito'])
  } catch {
    /* already gone */
  }
}

if (failures) {
  console.log('HOTKEY: FALHA')
  process.exit(1)
}
console.log(`HOTKEY: PASSA - a tecla abriu e fechou o ditado em ${GAPS_MS.length} intervalos`)
process.exit(0)
