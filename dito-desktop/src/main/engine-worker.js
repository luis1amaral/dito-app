// Recognizer on its own thread: loading a model takes seconds and would freeze the main process.
// Recognizer configs ported from stablyai/orca (MIT) -- src/main/speech/stt-worker.ts.
const { parentPort, workerData } = require('node:worker_threads')
const fs = require('node:fs')
const path = require('node:path')

const SAMPLE_RATE = 16000
let sherpa = null
let recognizer = null
let isStreaming = false

// Copied from stablyai/orca (MIT) -- src/main/speech/stt-audio-resample.ts
function resampleToRate(samples, inputRate, outputRate) {
  if (samples.length === 0 || inputRate === outputRate) return samples
  const n = Math.max(1, Math.round((samples.length * outputRate) / inputRate))
  const out = new Float32Array(n)
  const ratio = inputRate / outputRate
  for (let i = 0; i < n; i += 1) {
    const idx = i * ratio
    const left = Math.floor(idx)
    const right = Math.min(left + 1, samples.length - 1)
    const weight = idx - left
    out[i] = samples[left] * (1 - weight) + samples[right] * weight
  }
  return out
}

// Models name their files differently (encoder.int8.onnx vs tiny-encoder.onnx vs
// encoder-epoch-99-avg-1.onnx), so resolve by role instead of by exact name.
function resolveFile(names, role, dir, ext = '.onnx') {
  const match = names.find((n) => n.includes(role) && n.endsWith(ext))
  if (!match) throw new Error(`no *${role}*${ext} among: ${names.join(', ')}`)
  return path.join(dir, match)
}

function resolveTokens(names, dir) {
  const match = names.find((n) => n.endsWith('tokens.txt'))
  if (!match) throw new Error('no tokens.txt in the model directory')
  return path.join(dir, match)
}

function buildRecognizer(manifest, dir) {
  const names = fs.readdirSync(dir)
  const tokens = resolveTokens(names, dir)
  const base = { tokens, numThreads: 2, provider: 'cpu', debug: 0 }
  const feat = { featConfig: { sampleRate: SAMPLE_RATE, featureDim: 80 } }
  const endpoint = { enableEndpoint: 0 }

  if (manifest.streaming && manifest.type === 'transducer') {
    return sherpa.OnlineRecognizer
      ? new sherpa.OnlineRecognizer({
          ...feat,
          modelConfig: {
            transducer: {
              encoder: resolveFile(names, 'encoder', dir),
              decoder: resolveFile(names, 'decoder', dir),
              joiner: resolveFile(names, 'joiner', dir)
            },
            ...base
          },
          decodingMethod: 'greedy_search',
          ...endpoint
        })
      : null
  }
  if (manifest.streaming && manifest.type === 'paraformer') {
    return new sherpa.OnlineRecognizer({
      ...feat,
      modelConfig: {
        paraformer: {
          encoder: resolveFile(names, 'encoder', dir),
          decoder: resolveFile(names, 'decoder', dir)
        },
        ...base
      },
      decodingMethod: 'greedy_search',
      ...endpoint
    })
  }
  if (manifest.type === 'whisper') {
    return new sherpa.OfflineRecognizer({
      ...feat,
      modelConfig: {
        whisper: {
          encoder: resolveFile(names, 'encoder', dir),
          decoder: resolveFile(names, 'decoder', dir)
        },
        ...base
      },
      decodingMethod: 'greedy_search'
    })
  }
  if (manifest.type === 'nemo-ctc') {
    return new sherpa.OfflineRecognizer({
      ...feat,
      modelConfig: { nemoCtc: { model: resolveFile(names, 'model', dir) }, ...base },
      decodingMethod: 'greedy_search'
    })
  }
  if (manifest.type === 'senseVoice') {
    return new sherpa.OfflineRecognizer({
      ...feat,
      modelConfig: {
        // Empty language = auto-detect (zh/en/ja/ko/yue).
        senseVoice: { model: resolveFile(names, 'model', dir), language: '', useInverseTextNormalization: 1 },
        ...base
      },
      decodingMethod: 'greedy_search'
    })
  }
  return new sherpa.OfflineRecognizer({
    ...feat,
    modelConfig: {
      transducer: {
        encoder: resolveFile(names, 'encoder', dir),
        decoder: resolveFile(names, 'decoder', dir),
        joiner: resolveFile(names, 'joiner', dir)
      },
      ...base
    },
    decodingMethod: 'greedy_search'
  })
}

try {
  sherpa = require(workerData.sherpaPath)
  const manifest = workerData.manifest
  isStreaming = !!manifest.streaming
  const startedAt = Date.now()
  recognizer = buildRecognizer(manifest, workerData.modelDir)
  if (!recognizer) throw new Error('unsupported model type: ' + manifest.type)
  parentPort.postMessage({ kind: 'ready', ms: Date.now() - startedAt })
} catch (err) {
  parentPort.postMessage({ kind: 'error', error: String(err && err.message ? err.message : err) })
}

// Decode in windows: one call with a whole dictation grows the tensor with duration until a
// >=2 GiB allocation kills the app (Orca issue #7925).
const MAX_WINDOW_SECONDS = 20

function decodeOffline(samples) {
  const perWindow = MAX_WINDOW_SECONDS * SAMPLE_RATE
  const parts = []
  for (let i = 0; i < samples.length; i += perWindow) {
    const window = samples.subarray(i, Math.min(i + perWindow, samples.length))
    if (window.length < SAMPLE_RATE * 0.1) continue
    const stream = recognizer.createStream()
    stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: window })
    recognizer.decode(stream)
    const text = (recognizer.getResult(stream).text || '').trim()
    if (text) parts.push(text)
  }
  return parts.join(' ').trim()
}

// A streaming model still works push-to-talk: feed the whole take, then read the final result.
function decodeStreaming(samples) {
  const stream = recognizer.createStream()
  const chunk = SAMPLE_RATE
  for (let i = 0; i < samples.length; i += chunk) {
    stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: samples.subarray(i, Math.min(i + chunk, samples.length)) })
    while (recognizer.isReady(stream)) recognizer.decode(stream)
  }
  stream.inputFinished()
  while (recognizer.isReady(stream)) recognizer.decode(stream)
  return (recognizer.getResult(stream).text || '').trim()
}

parentPort.on('message', (msg) => {
  if (msg.kind !== 'transcribe' || !recognizer) return
  try {
    const samples = resampleToRate(Float32Array.from(msg.samples), msg.sampleRate, SAMPLE_RATE)
    const startedAt = Date.now()
    const text = isStreaming ? decodeStreaming(samples) : decodeOffline(samples)
    parentPort.postMessage({
      kind: 'text',
      id: msg.id,
      text,
      ms: Date.now() - startedAt,
      seconds: samples.length / SAMPLE_RATE
    })
  } catch (err) {
    parentPort.postMessage({ kind: 'text', id: msg.id, text: '', error: String(err.message || err) })
  }
})
