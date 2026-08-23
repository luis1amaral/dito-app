// Regressao do motor: replica cada fixture e reprova por WER, pontuacao ou lentidao.
// Roda em Node puro de proposito -- a prova de que o addon carrega no Electron e da fumaca.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const AQUI = path.dirname(fileURLToPath(import.meta.url))
const FIXTURES = path.join(AQUI, 'fixtures')
const SAMPLE_RATE = 16000
const MODEL_DIR =
  process.env.DITO_MODEL_DIR ||
  path.join(process.env.APPDATA, 'orca', 'speech-models', 'parakeet-tdt-0.6b-v3-int8')

// Copiado de stablyai/orca (MIT) -- src/main/speech/stt-audio-resample.ts
function resampleToRate(samples, entrada, saida) {
  if (samples.length === 0 || entrada === saida) return samples
  const n = Math.max(1, Math.round((samples.length * saida) / entrada))
  const out = new Float32Array(n)
  const ratio = entrada / saida
  for (let i = 0; i < n; i += 1) {
    const idx = i * ratio
    const e = Math.floor(idx)
    const d = Math.min(e + 1, samples.length - 1)
    const p = idx - e
    out[i] = samples[e] * (1 - p) + samples[d] * p
  }
  return out
}

// Acento fora, pontuacao fora, caixa fora: o WER mede palavra errada, nao teclado.
function normalizar(t) {
  return t
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
}

function wer(esperado, obtido) {
  const a = normalizar(esperado)
  const b = normalizar(obtido)
  if (a.length === 0) return b.length === 0 ? 0 : 1
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)])
  for (let j = 0; j <= b.length; j += 1) d[0][j] = j
  for (let i = 1; i <= a.length; i += 1) {
    for (let j = 1; j <= b.length; j += 1) {
      d[i][j] = Math.min(
        d[i - 1][j] + 1,
        d[i][j - 1] + 1,
        d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      )
    }
  }
  return d[a.length][b.length] / a.length
}

function lerWav(arquivo) {
  const buf = fs.readFileSync(arquivo)
  if (buf.toString('ascii', 0, 4) !== 'RIFF') throw new Error('nao e WAV RIFF')
  let pos = 12
  let fmt = null
  while (pos + 8 <= buf.length) {
    const id = buf.toString('ascii', pos, pos + 4)
    const tam = buf.readUInt32LE(pos + 4)
    const corpo = pos + 8
    if (id === 'fmt ') {
      fmt = { canais: buf.readUInt16LE(corpo + 2), rate: buf.readUInt32LE(corpo + 4), bits: buf.readUInt16LE(corpo + 14) }
    } else if (id === 'data') {
      if (!fmt || fmt.bits !== 16) throw new Error('esperado PCM 16-bit')
      const mono = new Float32Array(Math.floor(tam / 2 / fmt.canais))
      for (let i = 0; i < mono.length; i += 1) mono[i] = buf.readInt16LE(corpo + i * fmt.canais * 2) / 32768
      return { samples: mono, rate: fmt.rate }
    }
    pos = corpo + tam + (tam % 2)
  }
  throw new Error('sem chunk data')
}

const falhas = []
function reprovar(msg) {
  falhas.push(msg)
  console.log(`   REPROVA: ${msg}`)
}

const cfg = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'expected.json'), 'utf8'))
if (!cfg.fixtures?.length) {
  console.error('ENGINE: FALHA - nenhuma fixture em expected.json')
  process.exit(1)
}

for (const f of ['encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt']) {
  if (!fs.existsSync(path.join(MODEL_DIR, f))) {
    console.error(`ENGINE: FALHA - modelo incompleto, falta ${f} em ${MODEL_DIR}`)
    process.exit(1)
  }
}

const sherpa = require('sherpa-onnx-node')
const t0 = Date.now()
const recognizer = new sherpa.OfflineRecognizer({
  featConfig: { sampleRate: SAMPLE_RATE, featureDim: 80 },
  modelConfig: {
    transducer: {
      encoder: path.join(MODEL_DIR, 'encoder.int8.onnx'),
      decoder: path.join(MODEL_DIR, 'decoder.int8.onnx'),
      joiner: path.join(MODEL_DIR, 'joiner.int8.onnx')
    },
    tokens: path.join(MODEL_DIR, 'tokens.txt'),
    numThreads: 2,
    provider: 'cpu',
    debug: 0
  },
  decodingMethod: 'greedy_search'
})
console.log(`ENGINE: modelo carregado em ${Date.now() - t0} ms · ${cfg.fixtures.length} fixture(s)`)

for (const fx of cfg.fixtures) {
  const arquivo = path.join(FIXTURES, fx.arquivo)
  console.log('')
  console.log(`-- ${fx.arquivo}`)
  if (!fs.existsSync(arquivo)) {
    reprovar(`fixture ausente: ${fx.arquivo}`)
    continue
  }
  const audio = lerWav(arquivo)
  const amostras = resampleToRate(audio.samples, audio.rate, SAMPLE_RATE)
  const duracao = amostras.length / SAMPLE_RATE

  const inicio = Date.now()
  const stream = recognizer.createStream()
  stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: new Float32Array(amostras.length) }) // MUTATION
  recognizer.decode(stream)
  const texto = (recognizer.getResult(stream).text || '').trim()
  const ms = Date.now() - inicio
  const xreal = duracao / (ms / 1000)
  const taxa = wer(fx.esperado, texto)

  console.log(`   esperado: ${fx.esperado}`)
  console.log(`   obtido:   ${texto || '(VAZIO)'}`)
  console.log(`   WER ${(taxa * 100).toFixed(1)}%  ·  ${ms} ms  ·  ${xreal.toFixed(1)}x tempo real`)

  if (taxa > fx.werMax) reprovar(`${fx.arquivo}: WER ${(taxa * 100).toFixed(1)}% acima do teto ${(fx.werMax * 100).toFixed(0)}%`)
  if (fx.exigePontuacao && !/[.,!?;:]/.test(texto)) reprovar(`${fx.arquivo}: sem pontuacao`)
  if (fx.exigeDigitos && !/\d/.test(texto)) reprovar(`${fx.arquivo}: sem digito`)
  if (fx.minTempoReal && xreal < fx.minTempoReal) reprovar(`${fx.arquivo}: ${xreal.toFixed(1)}x abaixo do minimo ${fx.minTempoReal}x`)
}

console.log('')
if (falhas.length) {
  console.log(`ENGINE: FALHA - ${falhas.length} reprovacao(oes)`)
  process.exit(1)
}
console.log('ENGINE: PASSA')
process.exit(0)
