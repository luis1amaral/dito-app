// Owns the recognizer thread and nothing else.
import { Worker } from 'node:worker_threads'
import { join } from 'node:path'
import type { EngineMessage, ModelManifest } from '../shared/models'
import { log } from './logger'
import { dirFor } from './models'

export type OnText = (m: Extract<EngineMessage, { kind: 'text' }>) => void
export type OnSegment = (text: string) => void

let worker: Worker | null = null
let ready = false
let nextId = 0

export function isReady(): boolean {
  return ready
}

export function start(manifest: ModelManifest, onText: OnText, onSegment: OnSegment): void {
  ready = false
  const modelDir = dirFor(manifest.id)
  log('engine: model at ' + modelDir)
  worker = new Worker(join(__dirname, 'engine-worker.js'), {
    workerData: {
      modelDir,
      sherpaPath: require.resolve('sherpa-onnx-node'),
      manifest: {
        id: manifest.id,
        type: manifest.type,
        streaming: manifest.streaming,
        modelingUnit: manifest.modelingUnit
      }
    }
  })
  worker.on('message', (m: EngineMessage) => {
    if (m.kind === 'ready') {
      ready = true
      log('engine: ready in ' + m.ms + ' ms')
      // The smoke gate waits for this exact line before it measures anything.
      log('boot completo')
    } else if (m.kind === 'error') {
      log('engine: FAILED - ' + m.error)
    } else if (m.kind === 'segment') {
      onSegment(m.text)
    } else {
      onText(m)
    }
  })
  worker.on('error', (e: Error) => log('engine: thread error - ' + e.message))
}

export async function stop(): Promise<void> {
  ready = false
  if (worker) {
    await worker.terminate()
    worker = null
  }
}

export function feed(samples: Float32Array, sampleRate: number): void {
  worker?.postMessage({ kind: 'feed', samples, sampleRate })
}

export function flush(): void {
  if (!worker) return
  nextId += 1
  worker.postMessage({ kind: 'flush', id: nextId })
}
