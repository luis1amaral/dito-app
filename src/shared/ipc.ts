// Every IPC channel, argument and return declared once; why in docs/decisoes.md.
import type { Config } from './config'
import type { Lang } from './i18n'
import type { ModelRow } from './models'

export type DictationPhase = 'idle' | 'recording' | 'transcribing' | 'pasted' | 'done' | 'error'

export type PillState = { phase: DictationPhase; detail: string }

export type DownloadProgress = { id: string; file: string; done: number; total: number }

export type HookStatus = { installed: boolean; error: number; seen: number; pumps: number }

export type UpdateState = {
  state: 'idle' | 'checking' | 'downloading' | 'ready' | 'ok' | 'error'
  text: string
}

export type AppStatus = {
  engineReady: boolean
  hook: HookStatus
  update: UpdateState
  modelId: string | null
  modelLabel: string | null
  downloading: DownloadProgress | null
  modelError: string | null
  version: string
}

export type HistoryEntry = { at: string; text: string }

export type ReviewPayload = { text: string; targetTitle: string; targetKind: string }

export type ReviewResult = { action: 'send'; text: string } | { action: 'discard' }

/** Channels the renderer invokes and awaits. */
export type InvokeMap = {
  'config:read': { arg: void; ret: Config }
  'config:write': { arg: Partial<Config>; ret: Config }
  'status:read': { arg: void; ret: AppStatus }
  'history:read': { arg: void; ret: HistoryEntry[] }
  'history:clear': { arg: void; ret: true }
  'models:list': { arg: void; ret: ModelRow[] }
  'models:use': { arg: string; ret: ModelRow[] }
  'models:download': { arg: string; ret: ModelRow[] }
  'models:delete': { arg: string; ret: ModelRow[] }
  'models:retry': { arg: void; ret: { error: string | null } }
  'update:check': { arg: void; ret: UpdateState }
  'i18n:lang': { arg: void; ret: Lang }
  'review:resolve': { arg: ReviewResult; ret: void }
  /** The card asks for its payload on load; neither side may depend on ordering. */
  'review:pending': { arg: void; ret: ReviewPayload | null }
}

/** Messages the renderer sends without waiting. */
export type SendMap = {
  // Float32Array crosses IPC by structured clone: no JSON, no per-sample boxing.
  'audio:chunk': { samples: Float32Array; sampleRate: number }
  'audio:end': void
  'renderer-log': string
}

/** Messages the main process pushes to a window. */
export type EventMap = {
  state: PillState
  /** Text decoded while the person is still speaking, so a long take is never lost. */
  partial: { text: string }
  record: { microphone: string | null }
  stop: void
  'models:progress': DownloadProgress | null
  'review:show': ReviewPayload
}

export type InvokeChannel = keyof InvokeMap
export type SendChannel = keyof SendMap
export type EventChannel = keyof EventMap

/** What the preload exposes as window.api; the screens see nothing else. */
export type RendererApi = {
  invoke<C extends InvokeChannel>(channel: C, arg?: InvokeMap[C]['arg']): Promise<InvokeMap[C]['ret']>
  send<C extends SendChannel>(channel: C, payload: SendMap[C]): void
  on<C extends EventChannel>(channel: C, listener: (payload: EventMap[C]) => void): () => void
}
