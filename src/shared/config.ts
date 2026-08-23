// The one place the config shape is declared; why it matters in docs/decisoes.md.
import { LANGS, type Lang, type MessageKey } from './i18n'

export const HOTKEYS = ['F8', 'F9', 'F10', 'F11', 'F12', 'ScrollLock', 'Pause'] as const
export type HotKey = (typeof HOTKEYS)[number]

export const MODES = ['toggle', 'hold'] as const
export type Mode = (typeof MODES)[number]

export const REVIEWS = ['no-target', 'always', 'never'] as const
export type Review = (typeof REVIEWS)[number]

// Values map to i18n keys, not to text, so the label follows the screen's language.
export const REVIEW_LABEL_KEYS: Record<Review, MessageKey> = {
  'no-target': 'reviewLabelNoTarget',
  always: 'reviewLabelAlways',
  never: 'reviewLabelNever'
}

// Labels live next to the values so a screen cannot invent an option the code does not accept.
export const MODE_LABEL_KEYS: Record<Mode, MessageKey> = {
  toggle: 'modeLabelToggle',
  hold: 'modeLabelHold'
}

export type Config = {
  key: HotKey
  mode: Mode
  microphone: string | null
  /** Types the text into the window that had focus when the key went down. */
  autoPaste: boolean
  review: Review
  /** Presses Enter after pasting, so a typed command actually runs. */
  pressEnter: boolean
  /** Puts back whatever was on the clipboard before we used it. */
  restoreClipboard: boolean
  model: string
  lang: 'auto' | Lang
}

export const DEFAULT_CONFIG: Config = {
  key: 'F10',
  mode: 'toggle',
  microphone: null,
  autoPaste: true,
  review: 'no-target',
  pressEnter: false,
  restoreClipboard: true,
  model: 'parakeet-tdt-0.6b-v3-int8',
  lang: 'auto'
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
  if (!REVIEWS.includes(merged.review)) merged.review = DEFAULT_CONFIG.review
  if (!HOTKEYS.includes(merged.key)) merged.key = DEFAULT_CONFIG.key
  if (merged.lang !== 'auto' && !LANGS.includes(merged.lang)) merged.lang = DEFAULT_CONFIG.lang
  return merged
}
