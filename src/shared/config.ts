// The one place the config shape is declared; why it matters in _docs/decisoes.md.
import { LANGS, type Lang, type MessageKey } from './i18n'

export const HOTKEYS = ['F8', 'F9', 'F10', 'F11', 'F12', 'ScrollLock', 'Pause'] as const
export type HotKey = (typeof HOTKEYS)[number]

export const MODES = ['toggle', 'hold'] as const
export type Mode = (typeof MODES)[number]

// Values map to i18n keys next to the union, so a screen cannot invent an option the code rejects.
export const MODE_LABEL_KEYS: Record<Mode, MessageKey> = {
  toggle: 'modeLabelToggle',
  hold: 'modeLabelHold'
}

export type Config = {
  key: HotKey
  mode: Mode
  microphone: string | null
  captureSystemAudio: boolean
  /** Types the text into the window that had focus when the key went down. */
  autoPaste: boolean
  /** Presses Enter after pasting, so a typed command actually runs. */
  pressEnter: boolean
  model: string
  lang: 'auto' | Lang
  openAtLogin: boolean
}

export const DEFAULT_CONFIG: Config = {
  key: 'F10',
  mode: 'toggle',
  microphone: null,
  captureSystemAudio: true,
  autoPaste: true,
  pressEnter: false,
  model: 'parakeet-tdt-0.6b-v3-int8',
  lang: 'auto',
  openAtLogin: false
}

// Values and field names were pt-BR before the rename; a stale one silently never matches.
const LEGACY_MODES: Record<string, Mode> = { alternar: 'toggle', segurar: 'hold' }
const LEGACY_FIELDS: Record<string, keyof Config> = {
  tecla: 'key',
  modo: 'mode',
  microfone: 'microphone',
  colarAuto: 'autoPaste',
  modelo: 'model'
}

export function migrate(saved: Record<string, unknown>): Config {
  const out: Record<string, unknown> = { ...saved }
  for (const [old, current] of Object.entries(LEGACY_FIELDS)) {
    if (out[old] !== undefined && out[current] === undefined) out[current] = out[old]
    delete out[old]
  }
  const mode = out.mode
  if (typeof mode === 'string' && LEGACY_MODES[mode]) out.mode = LEGACY_MODES[mode]

  const merged = { ...DEFAULT_CONFIG, ...out } as Config
  // A value outside the union would typecheck at compile time but arrive from an edited file.
  if (!MODES.includes(merged.mode)) merged.mode = DEFAULT_CONFIG.mode
  if (!HOTKEYS.includes(merged.key)) merged.key = DEFAULT_CONFIG.key
  if (merged.lang !== 'auto' && !LANGS.includes(merged.lang)) merged.lang = DEFAULT_CONFIG.lang
  return merged
}
