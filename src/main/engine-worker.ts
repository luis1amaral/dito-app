// Recognizer on its own thread; configs ported from stablyai/orca (MIT), stt-worker.ts.
import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import { parentPort, workerData } from 'node:worker_threads'
import { AudioChunker } from './audio-chunker'
import type { EngineInput, EngineMessage, EngineRequest } from '../shared/models'

const SAMPLE_RATE = 16000
const MAX_WINDOW_SECONDS = 20

type Manifest = EngineInput['manifest']
/* eslint-disable @typescript-eslint/no-explicit-any -- the sherpa addon ships no types */
type Sherpa = any

const port = parentPort
if (!port) throw new Error('engine-worker precisa rodar como worker_thread')

const input = workerData as EngineInput
let recognizer: any = null
let streaming = false

function post(message: EngineMessage): void {
  port!.postMessage(message)
}

// Copied from stablyai/orca (MIT) -- src/main/speech/stt-audio-resample.ts
function resampleToRate(samples: Float32Array, inputRate: number, outputRate: number): Float32Array {
  if (samples.length === 0 || inputRate === outputRate) return samples
  const n = Math.max(1, Math.round((samples.length * outputRate) / inputRate))
  const out = new Float32Array(n)
  const ratio = inputRate / outputRate
  for (let i = 0; i < n; i += 1) {
    const idx = i * ratio
    const left = Math.floor(idx)
    const right = Math.min(left + 1, samples.length - 1)
    const weight = idx - left
    out[i] = samples[left]! * (1 - weight) + samples[right]! * weight
  }
  return out
}

// Resolve by role, not by exact name: each model names its files differently.
function resolveFile(names: string[], role: string, dir: string, ext = '.onnx'): string {
  const match = names.find((n) => n.includes(role) && n.endsWith(ext))
  if (!match) throw new Error(`no *${role}*${ext} among: ${names.join(', ')}`)
  return join(dir, match)
}

function resolveTokens(names: string[], dir: string): string {
  const match = names.find((n) => n.endsWith('tokens.txt'))
  if (!match) throw new Error('no tokens.txt in the model directory')
  return join(dir, match)
}

function build(sherpa: Sherpa, manifest: Manifest, dir: string, language?: string): unknown {
  const names = readdirSync(dir)
  const base = { tokens: resolveTokens(names, dir), numThreads: 2, provider: 'cpu', debug: 0 }
  const feat = { featConfig: { sampleRate: SAMPLE_RATE, featureDim: 80 } }
  const greedy = { decodingMethod: 'greedy_search' }
  const encoderDecoder = (): { encoder: string; decoder: string } => ({
    encoder: resolveFile(names, 'encoder', dir),
    decoder: resolveFile(names, 'decoder', dir)
  })
  // Lazy on purpose: resolving the joiner eagerly threw before whisper/ctc reached their own branch.
  const transducer = (): Record<string, string> => ({
    ...encoderDecoder(),
    joiner: resolveFile(names, 'joiner', dir)
  })

  if (manifest.streaming) {
    const modelConfig =
      manifest.type === 'paraformer'
        ? { paraformer: encoderDecoder(), ...base }
        : { transducer: transducer(), ...base }
    return new sherpa.OnlineRecognizer({ ...feat, modelConfig, ...greedy, enableEndpoint: 0 })
  }
  if (manifest.type === 'whisper') {
    const whisper = { ...encoderDecoder(), language: language || '', task: 'transcribe' }
    return new sherpa.OfflineRecognizer({ ...feat, modelConfig: { whisper, ...base }, ...greedy })
  }
  if (manifest.type === 'nemo-ctc') {
    const nemoCtc = { model: resolveFile(names, 'model', dir) }
    return new sherpa.OfflineRecognizer({ ...feat, modelConfig: { nemoCtc, ...base }, ...greedy })
  }
  if (manifest.type === 'senseVoice') {
    // Empty language = auto-detect (zh/en/ja/ko/yue).
    const senseVoice = { model: resolveFile(names, 'model', dir), language: '', useInverseTextNormalization: 1 }
    return new sherpa.OfflineRecognizer({ ...feat, modelConfig: { senseVoice, ...base }, ...greedy })
  }
  return new sherpa.OfflineRecognizer({ ...feat, modelConfig: { transducer: transducer(), ...base }, ...greedy })
}

try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const sherpa = require(input.sherpaPath) as Sherpa
  streaming = input.manifest.streaming
  const startedAt = Date.now()
  recognizer = build(sherpa, input.manifest, input.modelDir, input.language)
  post({ kind: 'ready', ms: Date.now() - startedAt })
} catch (err) {
  post({ kind: 'error', error: (err as Error).message ?? String(err) })
}

// Decode in windows; a single unbounded call kills the app (docs/decisoes.md).
function decodeOffline(samples: Float32Array): string {
  const perWindow = MAX_WINDOW_SECONDS * SAMPLE_RATE
  const parts: string[] = []
  for (let i = 0; i < samples.length; i += perWindow) {
    const window = samples.subarray(i, Math.min(i + perWindow, samples.length))
    if (window.length < SAMPLE_RATE * 0.1) continue
    const stream = recognizer.createStream()
    stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: window })
    recognizer.decode(stream)
    const text = String(recognizer.getResult(stream).text ?? '').trim()
    if (text) parts.push(text)
  }
  return parts.join(' ').trim()
}

// A streaming model still works push-to-talk: feed the whole take, then read the final result.
function decodeStreaming(samples: Float32Array): string {
  const stream = recognizer.createStream()
  const chunk = SAMPLE_RATE
  for (let i = 0; i < samples.length; i += chunk) {
    stream.acceptWaveform({ sampleRate: SAMPLE_RATE, samples: samples.subarray(i, Math.min(i + chunk, samples.length)) })
    while (recognizer.isReady(stream)) recognizer.decode(stream)
  }
  stream.inputFinished()
  while (recognizer.isReady(stream)) recognizer.decode(stream)
  return String(recognizer.getResult(stream).text ?? '').trim()
}

const chunker = new AudioChunker()
let started = 0

function decode(samples: Float32Array): string {
  return streaming ? decodeStreaming(samples) : decodeOffline(samples)
}

port.on('message', (msg: EngineRequest) => {
  if (!recognizer) return
  try {
    if (msg.kind === 'feed') {
      if (!started) started = Date.now()
      const samples = resampleToRate(msg.samples, msg.sampleRate, SAMPLE_RATE)
      for (const window of chunker.push(samples)) {
        const text = decode(window)
        if (text) post({ kind: 'segment', text })
      }
      return
    }
    // flush: decode the tail and close the take.
    const tail = chunker.flush()
    const text = tail && tail.length > SAMPLE_RATE * 0.1 ? decode(tail) : ''
    post({ kind: 'text', id: msg.id, text, ms: Date.now() - (started || Date.now()) })
    started = 0
  } catch (err) {
    chunker.reset()
    started = 0
    post({ kind: 'text', id: msg.kind === 'flush' ? msg.id : 0, text: '', ms: 0, error: (err as Error).message })
  }
})
