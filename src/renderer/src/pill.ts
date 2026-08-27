// The overlay: shows the phase and captures audio, same path as Orca.
import { applyI18n, t, type Lang, type MessageKey } from '../../shared/i18n'
import type { DictationPhase } from '../../shared/ipc'
import { DEAD_INPUT_MS, MicSignalWatch } from '../../shared/mic-signal'

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
  copied: 'pillCopied',
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
let micSource: MediaStreamAudioSourceNode | null = null
let sysSource: MediaStreamAudioSourceNode | null = null
let processor: ScriptProcessorNode | null = null
let micStream: MediaStream | null = null
let sysStream: MediaStream | null = null
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

const levels = Array.from<number>({ length: BAR_COUNT }).fill(0)
const signal = new MicSignalWatch()

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

async function record({
  microphone,
  desktopSourceId
}: {
  microphone: string | null
  desktopSourceId: string | null
}): Promise<void> {
  try {
    const audio: MediaTrackConstraints = {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true
    }
    if (microphone) audio.deviceId = { exact: microphone }
    micStream = await navigator.mediaDevices.getUserMedia({ audio })
  } catch (err) {
    window.api.send('renderer-log', 'mic getUserMedia failed: ' + (err as Error).message)
  }

  if (desktopSourceId) {
    try {
      sysStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: 'desktop',
            chromeMediaSourceId: desktopSourceId
          }
        } as unknown as MediaTrackConstraints,
        video: {
          mandatory: {
            chromeMediaSource: 'desktop',
            chromeMediaSourceId: desktopSourceId
          }
        } as unknown as MediaTrackConstraints
      })
      sysStream.getVideoTracks().forEach((track) => track.stop())
    } catch (err) {
      window.api.send('renderer-log', 'sys getUserMedia failed: ' + (err as Error).message)
    }
  }

  if (!micStream && !sysStream) {
    failCapture(t(lang, 'pillNoMicTitle'), t(lang, 'pillNoSoundDetail'))
    return
  }

  ctx = new AudioContext()
  sampleRate = ctx.sampleRate
  processor = ctx.createScriptProcessor(4096, 1, 1)
  pending = []
  pendingSamples = 0
  levels.fill(0)
  signal.start(Date.now())
  delete root.dataset.silent

  if (micStream && micStream.getAudioTracks().length > 0) {
    micSource = ctx.createMediaStreamSource(micStream)
    micSource.connect(processor)
    // Losing the track mid-capture is real (headset unplugged): say so instead of faking a recording.
    micStream.getAudioTracks()[0]?.addEventListener('ended', () => {
      window.api.send('renderer-log', 'mic audio track ended')
      if (!sysStream) failCapture(t(lang, 'pillMicLostTitle'), t(lang, 'pillMicLostDetail'))
    })
  }

  if (sysStream && sysStream.getAudioTracks().length > 0) {
    sysSource = ctx.createMediaStreamSource(sysStream)
    sysSource.connect(processor)
    sysStream.getAudioTracks()[0]?.addEventListener('ended', () => {
      window.api.send('renderer-log', 'system audio track ended')
    })
  }

  processor.onaudioprocess = (e): void => {
    const block = e.inputBuffer.getChannelData(0)
    // No length cap: flushPending ships every second, so nothing accumulates here to cap.
    pending.push(new Float32Array(block))
    pendingSamples += block.length
    if (pendingSamples >= sampleRate) flushPending()
    let sum = 0
    for (let i = 0; i < block.length; i += 8) sum += block[i]! * block[i]!
    const rms = Math.sqrt(sum / (block.length / 8))
    levels.pop()
    levels.unshift(Math.min(1, rms * 8))
    paintWave()

    const dead = signal.isDead(rms, Date.now())
    if (dead && !root.dataset.silent) {
      failCapture(t(lang, 'pillNoSoundTitle'), t(lang, 'pillNoSoundDetail'))
      window.api.send('renderer-log', 'nada chega do audio ha ' + DEAD_INPUT_MS + ' ms')
    } else if (!dead && root.dataset.silent) {
      delete root.dataset.silent
      title.textContent = t(lang, 'pillRecording')
      phrase.textContent = ''
    }
  }
  processor.connect(ctx.destination)
}

function stop(): void {
  processor?.disconnect()
  micSource?.disconnect()
  sysSource?.disconnect()
  micStream?.getTracks().forEach((track) => track.stop())
  sysStream?.getTracks().forEach((track) => track.stop())
  void ctx?.close()
  processor = null
  micSource = null
  sysSource = null
  micStream = null
  sysStream = null
  ctx = null

  flushPending()
  window.api.send('audio:end', undefined)
}

window.api.on('record', (options) => void ready.then(() => record(options)))
window.api.on('stop', () => stop())
