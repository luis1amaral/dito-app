// Model types shared by the catalog, the engine worker and the screens.

export type ModelType = 'transducer' | 'paraformer' | 'whisper' | 'nemo-ctc' | 'senseVoice'

export type ModelFile = {
  name: string
  bytes: number
  sha256: string
  url: string
}

export type ModelManifest = {
  id: string
  label: string
  description: string
  type: ModelType
  language: string
  streaming: boolean
  modelingUnit: string | null
  isDefault: boolean
  files: ModelFile[]
}

/** What a screen needs to draw one row; never a filesystem path. */
export type ModelRow = {
  id: string
  label: string
  description: string
  language: string
  type: ModelType
  streaming: boolean
  isDefault: boolean
  bytes: number
  installed: boolean
  active: boolean
  /** False while it is the only model on disk: the user must never end up with none. */
  canDelete: boolean
}

/** What the engine worker needs to build the right recognizer. */
export type EngineInput = {
  modelDir: string
  sherpaPath: string
  manifest: Pick<ModelManifest, 'id' | 'type' | 'streaming' | 'modelingUnit'>
}

export type EngineMessage =
  | { kind: 'ready'; ms: number }
  | { kind: 'error'; error: string }
  /** One decoded window, emitted while the take is still going. */
  | { kind: 'segment'; text: string }
  | { kind: 'text'; id: number; text: string; ms: number; seconds?: number; error?: string }

export type EngineRequest =
  | { kind: 'feed'; samples: Float32Array; sampleRate: number }
  | { kind: 'flush'; id: number }
