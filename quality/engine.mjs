// Engine regression: replays every fixture and fails on WER, punctuation or slowness.
// Plain Node on purpose -- proving the addon loads inside Electron is the smoke gate's job.
import fs from 'node:fs'
import path from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const HERE = path.dirname(fileURLToPath(import.meta.url))
const FIXTURES = path.join(HERE, 'fixtures')
const SAMPLE_RATE = 16000
const MODEL_NAME = 'parakeet-tdt-0.6b-v3-int8'

// Same directory the app writes to (src/main/paths.ts); the legacy one is where Orca left its copy.
function modelDirs() {
  if (process.env.DITO_MODEL_DIR) return [process.env.DITO_MODEL_DIR]
  const data =
    process.platform === 'linux'
      ? process.env.XDG_DATA_HOME || path.join(homedir(), '.local', 'share')
      : process.env.APPDATA || path.join(homedir(), 'AppData', 'Roaming')
  return [path.join(data, 'dito', 'speech-models', MODEL_NAME), path.join(data, 'orca', 'speech-models', MODEL_NAME)]
}

const NEEDED = ['encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt']
const MODEL_DIR = modelDirs().find((dir) => NEEDED.every((f) => fs.existsSync(path.join(dir, f))))

// Adapted from stablyai/orca (MIT) -- src/main/speech/stt-audio-resample.ts
function resampleToRate(samples, from, to) {
  if (samples.length === 0 || from === to) return samples
  const n = Math.max(1, Math.round((samples.length * to) / from))
  const out = new Float32Array(n)
  const ratio = from / to
  for (let i = 0; i < n; i += 1) {
    const idx = i * ratio
    const lo = Math.floor(idx)
    const hi = Math.min(lo + 1, samples.length - 1)
    const frac = idx - lo
    out[i] = samples[lo] * (1 - frac) + samples[hi] * frac
  }
  return out
}

// Accents, punctuation and case out: WER measures the wrong word, not the keyboard.
function normalize(t) {
  return t
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
}

function wer(expected, got) {
  const a = normalize(expected)
  const b = normalize(got)
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

function readWav(file) {
  const buf = fs.readFileSync(file)
  if (buf.toString('ascii', 0, 4) !== 'RIFF') throw new Error('nao e WAV RIFF')
  let pos = 12
  let fmt = null
  while (pos + 8 <= buf.length) {
    const id = buf.toString('ascii', pos, pos + 4)
    const size = buf.readUInt32LE(pos + 4)
    const body = pos + 8
    if (id === 'fmt ') {
      fmt = { channels: buf.readUInt16LE(body + 2), rate: buf.readUInt32LE(body + 4), bits: buf.readUInt16LE(body + 14) }
    } else if (id === 'data') {
      if (!fmt || fmt.bits !== 16) throw new Error('esperado PCM 16-bit')
      const mono = new Float32Array(Math.floor(size / 2 / fmt.channels))
      for (let i = 0; i < mono.length; i += 1) mono[i] = buf.readInt16LE(body + i * fmt.channels * 2) / 32768
      return { samples: mono, rate: fmt.rate }
    }
    pos = body + size + (size % 2)
  }
  throw new Error('sem chunk data')
}

const failures = []
function fail(msg) {
  failures.push(msg)
  console.log(`   REPROVA: ${msg}`)
}

const cfg = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'expected.json'), 'utf8'))
if (!cfg.fixtures?.length) {
  console.error('ENGINE: FALHA - nenhuma fixture em expected.json')
  process.exit(1)
}

if (!MODEL_DIR) {
  console.error('ENGINE: FALHA - modelo ' + MODEL_NAME + ' nao encontrado em: ' + modelDirs().join(' | '))
  process.exit(1)
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
console.log(`ENGINE: modelo carregado em ${Date.now() - t0} ms · ${cfg.fixtures.length} fixture(s) · ${MODEL_DIR}`)

for (const fx of cfg.fixtures) {
  const file = path.join(FIXTURES, fx.file)
  console.log('')
  console.log(`-- ${fx.file}`)
  if (!fs.existsSync(file)) {
    fail(`fixture ausente: ${fx.file}`)
    continue
  }
  const audio = readWav(file)
  const samples = resampleToRate(audio.samples, audio.rate, SAMPLE_RATE)
  const seconds = samples.length / SAMPLE_RATE

  const started = Date.now()
  const stream = recognizer.createStream()
  stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: samples })
  recognizer.decode(stream)
  const text = (recognizer.getResult(stream).text || '').trim()
  const ms = Date.now() - started
  const realtime = seconds / (ms / 1000)
  const rate = wer(fx.expected, text)

  console.log(`   esperado: ${fx.expected}`)
  console.log(`   obtido:   ${text || '(VAZIO)'}`)
  console.log(`   WER ${(rate * 100).toFixed(1)}%  ·  ${ms} ms  ·  ${realtime.toFixed(1)}x tempo real`)

  if (rate > fx.werMax) fail(`${fx.file}: WER ${(rate * 100).toFixed(1)}% acima do teto ${(fx.werMax * 100).toFixed(0)}%`)
  if (fx.requirePunctuation && !/[.,!?;:]/.test(text)) fail(`${fx.file}: sem pontuacao`)
  if (fx.requireDigits && !/\d/.test(text)) fail(`${fx.file}: sem digito`)
  if (fx.minRealtime && realtime < fx.minRealtime) fail(`${fx.file}: ${realtime.toFixed(1)}x abaixo do minimo ${fx.minRealtime}x`)
}

console.log('')
if (failures.length) {
  console.log(`ENGINE: FALHA - ${failures.length} reprovacao(oes)`)
  process.exit(1)
}
console.log('ENGINE: PASSA')
process.exit(0)
