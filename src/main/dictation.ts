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
import { segmentDelta } from '../shared/join-segments'
import { HISTORY_FILE } from './paths'
import { log } from './logger'

let phase: DictationPhase = 'idle'
let recordingSince = 0
/** Everything decoded in this take, already joined. */
let spoken = ''
/** What is decoded but not yet typed, because the target was not focused at the time. */
let unsent = ''

// Last resort for a lost key-up in hold mode (docs/decisoes.md).
const MAX_HOLD_MS = Number(process.env['DITO_MAX_HOLD_MS'] ?? 180_000)

// Toggle has no key-up to end a take; this ends it out loud instead of recording forever.
const MAX_TAKE_MS = Number(process.env['DITO_MAX_TAKE_MS'] ?? 3_600_000)
let ceiling: ReturnType<typeof setTimeout> | null = null

// Above the 1400 ms window quality/paste-targets.mjs proves a paste lands in (docs/decisoes.md).
const CLIPBOARD_HANDOVER_MS = 1500

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
  ceiling = setTimeout(() => {
    log('take: teto de ' + MAX_TAKE_MS + ' ms atingido, encerrando e entregando o texto')
    stop()
  }, MAX_TAKE_MS)
  log('dictation: started')
}

export function stop(): void {
  if (phase !== 'recording') return
  if (ceiling) {
    clearTimeout(ceiling)
    ceiling = null
  }
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

const PRESS_ENTER_DELAY_MS = 120

function typeInto(text: string, pressEnter: boolean): boolean {
  const typed = native.paste(text)
  if (typed && pressEnter) setTimeout(() => native.sendEnter(), PRESS_ENTER_DELAY_MS)
  return typed
}

// Typed mid-take only while the target still has focus; otherwise it waits for the end.
export function onSegment(text: string): void {
  const delta = segmentDelta(spoken, text)
  spoken += delta
  windows.sendTo('pill', 'partial', { text: spoken })
  if (!delta) return
  // Concatenated raw: joinSegment trims, and the delta's own leading space is the word separator.
  if (!config.get().autoPaste || !native.available() || !native.targetIsForeground()) {
    unsent += delta
    return
  }
  const pending = unsent + delta
  unsent = ''
  if (!typeInto(pending, false)) unsent = pending
}

export function onText(m: Extract<EngineMessage, { kind: 'text' }>): void {
  // Same rule as onSegment: the tail carries its own separator, and joinSegment would eat it.
  const tail = segmentDelta(spoken, m.text ?? '')
  spoken += tail
  const rest = unsent + tail
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
    if (rest) typed = typeInto(rest, cfg.pressEnter)
    else {
      typed = true
      if (cfg.pressEnter) setTimeout(() => native.sendEnter(), PRESS_ENTER_DELAY_MS)
    }
    log('type: ' + typed + ' into ' + target.kind + ' "' + target.title + '"')
  }

  // Ctrl+V is the only guarantee; why it waits after a real paste is in docs/decisoes.md.
  if (typed) setTimeout(() => clipboard.writeText(spoken), CLIPBOARD_HANDOVER_MS)
  else clipboard.writeText(spoken)
  flash(typed ? 'pasted' : 'copied', spoken, typed ? 2000 : 2600)
}

export function bindKey(): void {
  if (!native.available()) return
  const key = config.get().key
  let lastDown = 0
  const bound = native.startHook(key, (e) => {
    // The action name comes from the addon, never repeated as a literal on this side.
    if (e.action !== native.action()) return
    // Read fresh: capturing the mode here once meant changing it in settings did nothing until restart.
    if (config.get().mode === 'hold') {
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
    'key: ' + key + ' mode=' + config.get().mode + ' bound=' + bound +
      ' installed=' + st.installed + ' error=' + st.error
  )
}

export function rebindKey(): void {
  native.stopHook()
  bindKey()
}
