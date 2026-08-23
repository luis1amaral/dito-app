// Prova cada portao no sentido contrario: recoloca um defeito conhecido e exige REPROVACAO.
// Portao que nunca reprovou nao e portao (REGRAS.md 2).
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const AQUI = path.dirname(fileURLToPath(import.meta.url))
const MOTOR = path.join(AQUI, 'engine.mjs')

const MUTACOES = [
  {
    nome: 'resample-neutralizado',
    porque: 'o renderer entrega 48 kHz; sem resample o motor recebe a taxa errada',
    aplicar: (s) =>
      s.replace(
        'if (samples.length === 0 || entrada === saida) return samples',
        'return samples // MUTATION'
      )
  },
  {
    nome: 'audio-mudo',
    porque: 'motor devolvendo vazio e a regressao que passa em silencio',
    aplicar: (s) =>
      s.replace(
        'stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: amostras })',
        'stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: new Float32Array(amostras.length) }) // MUTATION'
      )
  },
  {
    nome: 'modelo-ausente',
    porque: 'faltar arquivo do modelo tem de falhar alto, nunca passar batido',
    env: { DITO_MODEL_DIR: path.join(AQUI, 'nao-existe') }
  }
]

const original = fs.readFileSync(MOTOR, 'utf8')
let reprovouTudo = true

for (const m of MUTACOES) {
  process.stdout.write(`-- ${m.nome.padEnd(24)} `)
  let mutado = original
  if (m.aplicar) {
    mutado = m.aplicar(original)
    if (mutado === original) {
      console.log('ERRO: a mutacao nao casou com o codigo (o alvo mudou de nome?)')
      reprovouTudo = false
      continue
    }
    fs.writeFileSync(MOTOR, mutado)
  }
  const r = spawnSync(process.execPath, [MOTOR], {
    encoding: 'utf8',
    env: { ...process.env, ...m.env }
  })
  if (m.aplicar) fs.writeFileSync(MOTOR, original)

  if (r.status === 0) {
    console.log(`PASSOU MESMO MUTADO  <-- o portao e cego a: ${m.porque}`)
    reprovouTudo = false
  } else {
    console.log(`reprovou (exit ${r.status}) OK`)
  }
}

console.log('')
if (!reprovouTudo) {
  console.log('MUTATION: FALHA - existe defeito que o portao nao ve')
  process.exit(1)
}
console.log('MUTATION: PASSA - todo defeito plantado foi pego')
process.exit(0)
