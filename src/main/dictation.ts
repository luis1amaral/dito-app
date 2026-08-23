// The dictation flow: key -> record -> transcribe -> type. One state machine, one place.
import { clipboard } from 'electron'
import { appendFileSync } from 'node:fs'
import type { DictationPhase } from '../shared/ipc'
import type { EngineMessage } from '../shared/models'
import * as config from './config'
import * as engine from './engine'
import * as native from './native'
import * as tray from './tray'
import * as windows from './windows'
import { joinSegment } from '../shared/join-segments'
import { HISTORY_FILE } from './paths'
import { log } from './logger'

let phase: DictationPhase = 'idle'
let recordingSince = 0
/** Everything decoded in this take, already joined. */
let spoken = ''
/** What is decoded but not yet typed, because the target was not focused at the time. */
let unsent = ''

// Last resort for a lost key-up; matches the renderer buffer cap (docs/decisoes.md).
const MAX_HOLD_MS = Number(process.env['DITO_MAX_HOLD_MS'] ?? 180_000)

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
  spoken = ''
  unsent = ''
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

export function feedAudio(samples: Float32Array, sampleRate: number): void {
  engine.feed(samples, sampleRate)
}

export function endAudio(): void {
  engine.flush()
}

function remember(text: string): void {
  try {
    appendFileSync(HISTORY_FILE, JSON.stringify({ at: new Date().toISOString(), text }) + '\n')
  } catch {
    // History is a convenience; losing a line must not break the dictation.
  }
}

function typeInto(text: string, pressEnter: boolean): boolean {
  const typed = native.paste(text)
  if (typed && pressEnter) native.typeText('\r')
  return typed
}

// Typed mid-take only while the target still has focus; otherwise it waits for the end.
export function onSegment(text: string): void {
  const joined = joinSegment(spoken, text)
  const delta = joined.slice(spoken.length)
  spoken = joined
  windows.sendTo('pill', 'partial', { text: spoken })
  if (!delta) return
  if (!config.get().autoPaste || !native.available() || !native.targetIsForeground()) {
    unsent = joinSegment(unsent, delta)
    return
  }
  const pending = joinSegment(unsent, delta)
  unsent = ''
  if (!typeInto(pending, false)) unsent = pending
}

export function onText(m: Extract<EngineMessage, { kind: 'text' }>): void {
  const tail = (m.text ?? '').trim()
  spoken = joinSegment(spoken, tail)
  const rest = joinSegment(unsent, tail)
  unsent = ''
  const speed = m.seconds ? (m.seconds / (m.ms / 1000)).toFixed(1) : '?'
  log('transcribed: ' + m.ms + ' ms (' + speed + 'x) "' + spoken + '"')

  if (!spoken) {
    flash('error', 'não entendi', 1600)
    return
  }
  remember(spoken)

  const cfg = config.get()
  let typed = false
  if (cfg.autoPaste) {
    const target = native.currentTarget()
    typed = rest ? typeInto(rest, cfg.pressEnter) : true
    log('type: ' + typed + ' into ' + target.kind + ' "' + target.title + '"')
  }

  // Always last and always done: a window is always there, so Ctrl+V is the only guarantee.
  clipboard.writeText(spoken)
  flash(typed ? 'pasted' : 'copied', spoken, typed ? 2000 : 2600)
}

export function bindKey(): void {
  if (!native.available()) return
  const cfg = config.get()
  let lastDown = 0
  const bound = native.startHook(cfg.key, (e) => {
    // The action name comes from the addon, never repeated as a literal on this side.
    if (e.action !== native.action()) return
    if (cfg.mode === 'hold') {
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
