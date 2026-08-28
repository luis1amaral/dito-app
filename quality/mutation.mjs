// Proves every gate in reverse: puts a known defect back and demands a FAILURE.
// A gate that never failed is not a gate (_docs/PARIDADE.md).
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(HERE, '..')
const ENGINE = path.join(HERE, 'engine.mjs')

const engineGate = { cmd: process.execPath, args: [ENGINE] }
const sharedGate = { cmd: 'npx', args: ['tsx', path.join(HERE, 'shared.ts')] }
const leakGate = { cmd: 'npx', args: ['electron', path.join(HERE, 'audio-leak.mjs')] }
// The renderer defect only exists in the bundle, so this gate needs a rebuild on each side.
const rebuild = { cmd: 'npm', args: ['run', 'build'] }

const MUTATIONS = [
  {
    name: 'resample-neutralizado',
    why: 'o renderer entrega 48 kHz; sem resample o motor recebe a taxa errada',
    file: ENGINE,
    gate: engineGate,
    apply: (s) => s.replace('if (samples.length === 0 || from === to) return samples', 'return samples // MUTATION')
  },
  {
    name: 'audio-mudo',
    why: 'motor devolvendo vazio e a regressao que passa em silencio',
    file: ENGINE,
    gate: engineGate,
    apply: (s) =>
      s.replace(
        'stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: samples })',
        'stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: new Float32Array(samples.length) }) // MUTATION'
      )
  },
  {
    name: 'modelo-ausente',
    why: 'faltar arquivo do modelo tem de falhar alto, nunca passar batido',
    gate: engineGate,
    env: { DITO_MODEL_DIR: path.join(HERE, 'nao-existe') }
  },
  {
    name: 'emenda-sem-espaco',
    why: 'sem o separador os trechos saem colados: "quando eu.To falando" (defeito da 2.0.9)',
    file: path.join(ROOT, 'src', 'shared', 'join-segments.ts'),
    gate: sharedGate,
    apply: (s) => s.replace("return soFar + ' ' + piece", 'return soFar + piece // MUTATION')
  },
  {
    name: 'captura-sem-trava',
    why: 'sem o token de sessao, cancelar durante o getUserMedia deixa o microfone gravando sozinho',
    file: path.join(ROOT, 'src', 'renderer', 'src', 'pill.ts'),
    gate: leakGate,
    prepare: rebuild,
    restore: rebuild,
    apply: (s) => s.replaceAll('activeRecordId !== currentRecordId ||', 'currentRecordId < 0 || /* MUTATION */')
  }
]

function run({ cmd, args }, env) {
  return spawnSync(cmd, args, {
    cwd: ROOT,
    encoding: 'utf8',
    shell: process.platform === 'win32',
    env: { ...process.env, ...env }
  })
}

let allFailed = true

for (const m of MUTATIONS) {
  process.stdout.write(`-- ${m.name.padEnd(24)} `)
  const original = m.file ? fs.readFileSync(m.file, 'utf8') : null
  try {
    if (m.apply) {
      const mutated = m.apply(original)
      if (mutated === original) {
        console.log('ERRO: a mutacao nao casou com o codigo (o alvo mudou de nome?)')
        allFailed = false
        continue
      }
      fs.writeFileSync(m.file, mutated)
      // A prepare that fails would leave the gate running the previous artifact and passing blind.
      if (m.prepare && run(m.prepare).status !== 0) {
        console.log('ERRO: a preparacao da mutacao falhou (o codigo mutado nao compila?)')
        allFailed = false
        continue
      }
    }
    const r = run(m.gate, m.env)
    if (r.status === 0) {
      console.log(`PASSOU MESMO MUTADO  <-- o portao e cego a: ${m.why}`)
      allFailed = false
    } else {
      console.log(`reprovou (exit ${r.status}) OK`)
    }
  } finally {
    // Restoring in finally: a crash mid-run must never leave the source mutated on disk.
    if (original !== null) fs.writeFileSync(m.file, original)
    if (m.restore) run(m.restore)
  }
}

console.log('')
if (!allFailed) {
  console.log('MUTATION: FALHA - existe defeito que o portao nao ve')
  process.exit(1)
}
console.log('MUTATION: PASSA - todo defeito plantado foi pego')
process.exit(0)
