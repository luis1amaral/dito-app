// The dictation flow: key -> record -> transcribe -> review or paste. One state machine, one place.
import { clipboard } from 'electron'
import { appendFileSync } from 'node:fs'
import type { DictationPhase, ReviewResult } from '../shared/ipc'
import type { EngineMessage } from '../shared/models'
import * as config from './config'
import * as engine from './engine'
import * as native from './native'
import * as tray from './tray'
import * as windows from './windows'
import { HISTORY_FILE } from './paths'
import { joinSegment } from '../shared/join-segments'
import { log } from './logger'

let phase: DictationPhase = 'idle'

function setPhase(next: DictationPhase, detail = ''): void {
  phase = next
  tray.setPhase(next)
  if (next === 'idle') {
    windows.sendTo('pill', 'state', { phase: 'idle', detail: '' })
    // Let the exit animation finish before the window disappears.
    setTimeout(() => {
      if (phase === 'idle') windows.hidePill()
    }, 240)
    return
  }
  windows.showPill()
  windows.sendTo('pill', 'state', { phase: next, detail })
}

function flash(next: DictationPhase, detail: string, ms: number): void {
  setPhase(next, detail)
  setTimeout(() => {
    if (phase === next) setPhase('idle')
  }, ms)
}

// Only recording and transcribing are busy; refusing the key during a message felt dead.
function busy(): boolean {
  return phase === 'recording' || phase === 'transcribing'
}

export function start(): void {
  if (busy()) return
  if (!engine.isReady()) {
    flash('error', 'o motor ainda está carregando', 1600)
    return
  }
  live = ''
  recordingSince = Date.now()
  setPhase('recording')
  windows.sendTo('pill', 'record', { microphone: config.get().microphone })
  log('dictation: started')
}

export function stop(): void {
  if (phase !== 'recording') return
  setPhase('transcribing')
  windows.sendTo('pill', 'stop', undefined)
  log('dictation: stopped, transcribing')
}

let live = ''
let recordingSince = 0

// Last resort for a lost key-up; matches the renderer buffer cap (docs/decisoes.md).
const MAX_HOLD_MS = Number(process.env['DITO_MAX_HOLD_MS'] ?? 180_000)

export function feedAudio(samples: Float32Array, sampleRate: number): void {
  engine.feed(samples, sampleRate)
}

export function endAudio(): void {
  engine.flush()
}

// Text decoded mid-take: showing it is what makes a long dictation feel safe.
export function onSegment(text: string): void {
  live = joinSegment(live, text)
  windows.sendTo('pill', 'partial', { text: live })
}

function remember(text: string): void {
  try {
    appendFileSync(HISTORY_FILE, JSON.stringify({ at: new Date().toISOString(), text }) + '\n')
  } catch {
    // History is a convenience; losing a line must not break the dictation.
  }
}

function deliver(text: string): boolean {
  const cfg = config.get()
  if (!cfg.autoPaste || !native.available()) return false
  const target = native.currentTarget()
  // The clipboard belongs to the user: our paste borrows it and must give it back.
  const previous = cfg.restoreClipboard ? clipboard.readText() : null
  const pasted = native.paste(text)
  log('paste: ' + pasted + ' into ' + target.kind + ' "' + target.title + '"')
  if (pasted && cfg.pressEnter) native.typeText('\r')
  if (previous !== null) {
    // After the target consumed it; doing this sooner would race the paste.
    setTimeout(() => clipboard.writeText(previous), 400)
  }
  return pasted
}

export function onText(m: Extract<EngineMessage, { kind: 'text' }>): void {
  const text = joinSegment(live, m.text ?? '').trim()
  live = ''
  const speed = m.seconds ? (m.seconds / (m.ms / 1000)).toFixed(1) : '?'
  log('transcribed: ' + m.ms + ' ms (' + speed + 'x) "' + text + '"')
  if (!text) {
    flash('error', 'não entendi', 1600)
    return
  }
  remember(text)

  const target = native.currentTarget()
  if (needsReview(target)) {
    setPhase('idle')
    windows.showReview({ text, targetTitle: target.title, targetKind: target.kind })
    return
  }
  flash(deliver(text) ? 'pasted' : 'done', text, 2000)
}

// No remembered window means there was nowhere to type: show the card instead of losing the text.
function needsReview(target: native.TargetInfo): boolean {
  const mode = config.get().review
  if (mode === 'always') return true
  if (mode === 'never') return false
  return target.hwnd === 0 || !target.className
}

/** The review card answered: send pastes it, discard drops it. */
export function resolveReview(result: ReviewResult): void {
  windows.closeReview()
  if (result.action === 'discard') {
    log('review: descartado')
    // Silent discard felt like a bug; say it happened, then go quiet.
    flash('error', 'descartado', 1100)
    return
  }
  flash(deliver(result.text) ? 'pasted' : 'done', result.text, 2000)
}

export function bindKey(): void {
  if (!native.available()) return
  const cfg = config.get()
  let lastDown = 0
  const bound = native.startHook(cfg.key, (e) => {
    // The action name comes from the addon, never repeated as a literal on this side.
    if (e.action !== native.action()) return
    if (cfg.mode === 'hold') {
      // The tick carries the physical state; a swallowed key-up would leave this stuck recording.
      if (e.kind === 'tick') {
        if (phase !== 'recording') return
        const held = Date.now() - recordingSince
        if (!e.down && held > 300) stop()
        else if (held > MAX_HOLD_MS) {
          log('hold: teto de ' + MAX_HOLD_MS + ' ms atingido, encerrando sozinho')
          stop()
        }
        return
      }
      if (e.kind !== 'edge') return
      if (e.down) start()
      else stop()
      return
    }
    if (e.kind !== 'edge') return
    // Toggle: only the key-down counts; key-up is ignored on purpose.
    if (!e.down) return
    const now = Date.now()
    if (now - lastDown < 250) return
    lastDown = now
    if (phase === 'recording') stop()
    else start()
  })
  const st = native.hookStatus()
  log(
    'key: ' + cfg.key + ' mode=' + cfg.mode + ' bound=' + bound +
      ' installed=' + st.installed + ' error=' + st.error
  )
}

export function rebindKey(): void {
  native.stopHook()
  bindKey()
}
