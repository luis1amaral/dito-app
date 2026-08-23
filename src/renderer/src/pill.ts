// The overlay: shows the phase and captures audio, same path as Orca.
import { applyI18n, t, type Lang, type MessageKey } from '../../shared/i18n'
import type { DictationPhase } from '../../shared/ipc'

const root = document.body
const title = document.getElementById('title') as HTMLElement
const phrase = document.getElementById('phrase') as HTMLElement
const wave = document.getElementById('wave') as HTMLElement

const BAR_COUNT = 32
for (let i = 0; i < BAR_COUNT; i += 1) wave.appendChild(document.createElement('i'))
const bars = [...wave.children] as HTMLElement[]

const PHASE_KEYS: Record<DictationPhase, MessageKey> = {
  idle: 'appName',
  recording: 'pillRecording',
  transcribing: 'pillTranscribing',
  pasted: 'pillPasted',
  done: 'pillDone',
  error: 'pillError'
}

let lang: Lang = 'pt'
const ready = (async (): Promise<void> => {
  lang = await window.api.invoke('i18n:lang')
  applyI18n(document, lang)
  document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
})()

window.api.on('partial', ({ text }) => {
  if (root.dataset.phase === 'recording') phrase.textContent = text
})

window.api.on('state', ({ phase, detail }) => {
  root.dataset.phase = phase
  root.dataset.visible = phase === 'idle' ? '0' : '1'
  title.textContent = t(lang, PHASE_KEYS[phase])
  phrase.textContent = detail
  if (phase !== 'recording') {
    for (const b of bars) b.style.height = '3px'
    delete root.dataset.silent
  }
})

let ctx: AudioContext | null = null
let source: MediaStreamAudioSourceNode | null = null
let processor: ScriptProcessorNode | null = null
let stream: MediaStream | null = null
let pending: Float32Array[] = []
let pendingSamples = 0
let sampleRate = 0

// Ship about a second at a time: the engine cuts it into windows and answers while we still talk.
function flushPending(): void {
  if (!pendingSamples) return
  const all = new Float32Array(pendingSamples)
  let offset = 0
  for (const part of pending) {
    all.set(part, offset)
    offset += part.length
  }
  pending = []
  pendingSamples = 0
  window.api.send('audio:chunk', { samples: all, sampleRate })
}

const MAX_SECONDS = 180
const levels = Array.from<number>({ length: BAR_COUNT }).fill(0)

// Warm-up is by TIME: a count-based one fires the alarm early on a fast device.
const WARMUP_MS = 1200
const SILENCE_MS = 2000
const SILENCE_RMS = 0.006
let startedAt = 0
let quietSince = 0

// Center-out mapping so the newest level lands in the middle and travels to both edges.
function paintWave(): void {
  const mid = (BAR_COUNT - 1) / 2
  for (let i = 0; i < BAR_COUNT; i += 1) {
    const level = levels[Math.round(Math.abs(i - mid))] ?? 0
    const falloff = 1 - Math.abs(i - mid) / (mid + 4)
    bars[i]!.style.height = 3 + level * 21 * falloff + 'px'
  }
}

function failCapture(label: string, why: string): void {
  root.dataset.silent = '1'
  title.textContent = label
  phrase.textContent = why
}

async function record({ microphone }: { microphone: string | null }): Promise<void> {
  try {
    const audio: MediaTrackConstraints = {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true
    }
    if (microphone) audio.deviceId = { exact: microphone }
    stream = await navigator.mediaDevices.getUserMedia({ audio })
  } catch (err) {
    window.api.send('renderer-log', 'getUserMedia failed: ' + (err as Error).message)
    failCapture(t(lang, 'pillNoMicTitle'), (err as Error).message)
    return
  }
  ctx = new AudioContext()
  sampleRate = ctx.sampleRate
  source = ctx.createMediaStreamSource(stream)
  processor = ctx.createScriptProcessor(4096, 1, 1)
  pending = []
  pendingSamples = 0
  levels.fill(0)
  startedAt = Date.now()
  quietSince = 0
  delete root.dataset.silent
  let totalSamples = 0

  processor.onaudioprocess = (e): void => {
    const block = e.inputBuffer.getChannelData(0)
    // Safety cap: an unbounded buffer grows until the process dies.
    if (totalSamples < sampleRate * MAX_SECONDS) {
      pending.push(new Float32Array(block))
      pendingSamples += block.length
      totalSamples += block.length
      if (pendingSamples >= sampleRate) flushPending()
    }
    let sum = 0
    for (let i = 0; i < block.length; i += 8) sum += block[i]! * block[i]!
    const rms = Math.sqrt(sum / (block.length / 8))
    levels.pop()
    levels.unshift(Math.min(1, rms * 8))
    paintWave()

    const now = Date.now()
    if (now - startedAt < WARMUP_MS) return
    if (rms >= SILENCE_RMS) {
      quietSince = 0
      if (root.dataset.silent) {
        delete root.dataset.silent
        title.textContent = t(lang, 'pillRecording')
        phrase.textContent = ''
      }
      return
    }
    if (!quietSince) quietSince = now
    if (now - quietSince >= SILENCE_MS && !root.dataset.silent) {
      failCapture(t(lang, 'pillNoSoundTitle'), t(lang, 'pillNoSoundDetail'))
      window.api.send('renderer-log', 'sem sinal do microfone ha ' + SILENCE_MS + ' ms')
    }
  }
  source.connect(processor)
  processor.connect(ctx.destination)

  // Losing the track mid-capture is real (headset unplugged): say so instead of faking a recording.
  stream.getAudioTracks()[0]?.addEventListener('ended', () => {
    window.api.send('renderer-log', 'audio track ended on its own')
    failCapture(t(lang, 'pillMicLostTitle'), t(lang, 'pillMicLostDetail'))
  })
}

function stop(): void {
  processor?.disconnect()
  source?.disconnect()
  stream?.getTracks().forEach((track) => track.stop())
  void ctx?.close()
  processor = null
  source = null
  stream = null
  ctx = null

  flushPending()
  window.api.send('audio:end', undefined)
}

window.api.on('record', (options) => void ready.then(() => record(options)))
window.api.on('stop', () => stop())
