// Single entry point of the quality gate, on Windows and on Linux. Three states, on purpose:
//   exit 0 = PASSA        everything that exists here was proven
//   exit 1 = FALHA        some check failed
//   exit 2 = INCOMPLETO   a layer could not be proven on this platform -- NEVER read as green
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const ROOT = join(import.meta.dirname, '..')
const QUALITY = join(ROOT, 'quality')
const quick = process.argv.slice(2).some((a) => a === '--rapido' || a === '--quick')

// Gates that write app data must not touch the real profile: they would poison log and models.
const ISOLATED = { DITO_APPDATA: join(tmpdir(), 'dito-gate') }

const npx = (...args) => ({ cmd: 'npx', args })
const node = (script) => ({ cmd: process.execPath, args: [join(QUALITY, script)] })

const LAYERS = [
  { name: 'typecheck (o contrato compila?)', run: npx('tsc', '--noEmit') },
  { name: 'lint (oxlint)', run: npx('oxlint') },
  { name: 'regras do projeto', run: npx('tsx', join(QUALITY, 'code-quality.ts')) },
  { name: 'bundle (as telas compilam?)', run: npx('electron-vite', 'build') },
  { name: 'compartilhado (emenda, config, i18n)', run: npx('tsx', join(QUALITY, 'shared.ts')) },
  { name: 'motor (regressao por fixture)', run: node('engine.mjs') },
  { name: 'mutacao (portao reprova?)', run: node('mutation.mjs'), skippable: true },
  { name: 'modelos (baixa e trava?)', run: npx('tsx', join(QUALITY, 'models.mts')), env: ISOLATED },
  { name: 'cortador (corta no silencio?)', run: npx('tsx', join(QUALITY, 'chunker.ts')) },
  { name: 'sinal (pausa nao vira falha?)', run: npx('tsx', join(QUALITY, 'mic-signal.ts')) },
  { name: 'captura (cancelar solta o microfone?)', run: npx('electron', join(QUALITY, 'audio-leak.mjs')) },
  { name: 'nativo (hook instala?)', run: node('native.mjs') },
  { name: 'tecla (a tecla dita mesmo?)', run: node('hotkey.mjs'), only: 'win32' },
  { name: 'segurar (5 ciclos e teto)', run: node('hold.mjs'), only: 'win32' },
  { name: 'fumaca (o app sobe?)', run: { cmd: 'pwsh', args: ['-NoProfile', '-File', join(QUALITY, 'smoke.ps1')] }, only: 'win32' },
  { name: 'colagem (console cru)', run: node('paste-wiring.mjs'), only: 'win32' },
  { name: 'colagem (via gui)', run: node('paste-targets.mjs'), only: 'win32' },
  { name: 'colagem (x11)', run: npx('electron', join(QUALITY, 'paste-linux.js')), only: 'linux' },
  { name: 'feed (o app acha a versao?)', run: npx('tsx', join(QUALITY, 'update-feed.mts')), env: ISOLATED },
]

const PAINT = { PASSA: '\x1b[32m', FALHA: '\x1b[31m', PENDENTE: '\x1b[33m', PULADO: '\x1b[90m' }
const paint = (state, text) => `${PAINT[state] ?? ''}${text}\x1b[0m`

const results = []
for (const layer of LAYERS) {
  if (layer.only && layer.only !== process.platform) {
    results.push({ name: layer.name, state: 'PENDENTE', note: `só roda em ${layer.only}` })
    continue
  }
  if (layer.skippable && quick) {
    results.push({ name: layer.name, state: 'PULADO', note: '--rapido' })
    continue
  }
  console.log('\n' + paint('PASSA', '########## ' + layer.name))
  const { cmd, args } = layer.run
  const r = spawnSync(cmd, args, {
    cwd: ROOT,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: { ...process.env, ...layer.env },
  })
  const code = r.status ?? 1
  const state = code === 0 ? 'PASSA' : code === 2 ? 'PENDENTE' : 'FALHA'
  results.push({ name: layer.name, state, note: 'exit ' + code })
}

console.log('\n================ resultado ================')
for (const r of results) console.log(paint(r.state, r.state.padEnd(10) + r.name) + (r.note ? '  · ' + r.note : ''))

if (results.some((r) => r.state === 'FALHA')) {
  console.log(paint('FALHA', '\nVERIFICAR: FALHA'))
  process.exit(1)
}
if (results.some((r) => r.state === 'PENDENTE')) {
  console.log(paint('PENDENTE', '\nVERIFICAR: INCOMPLETO - ha camada sem prova aqui. Isto NAO e verde.'))
  process.exit(2)
}
console.log(paint('PASSA', '\nVERIFICAR: PASSA'))
process.exit(0)
