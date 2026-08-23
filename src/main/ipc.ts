// Every IPC handler, typed by the shared contract in src/shared/ipc.ts.
import { app, ipcMain } from 'electron'
import { readFileSync, unlinkSync } from 'node:fs'
import type { AppStatus, HistoryEntry, InvokeChannel, InvokeMap } from '../shared/ipc'
import type { Config } from '../shared/config'
import { t, type Lang } from '../shared/i18n'
import type { ModelRow } from '../shared/models'
import * as config from './config'
import * as dictation from './dictation'
import * as engine from './engine'
import * as models from './models'
import * as native from './native'
import * as updater from './updater'
import * as windows from './windows'
import { APPDATA, HISTORY_FILE } from './paths'
import { log } from './logger'

type Handler<C extends InvokeChannel> = (arg: InvokeMap[C]['arg']) => InvokeMap[C]['ret'] | Promise<InvokeMap[C]['ret']>

function handle<C extends InvokeChannel>(channel: C, fn: Handler<C>): void {
  ipcMain.handle(channel, (_event, arg: InvokeMap[C]['arg']) => fn(arg))
}

let downloading: AppStatus['downloading'] = null
let modelError: string | null = null

// 'auto' follows the OS locale so a fresh install speaks the user's language without asking.
function resolveLang(): Lang {
  const configured = config.get().lang
  if (configured !== 'auto') return configured
  return app.getLocale().startsWith('pt') ? 'pt' : 'en'
}

export function activeManifest(): ReturnType<typeof models.installed>[number] | undefined {
  const wanted = config.get().model
  if (models.isInstalled(wanted)) return models.CATALOG.find((m) => m.id === wanted)
  return models.installed()[0]
}

export function startEngine(): void {
  const manifest = activeManifest()
  if (!manifest) {
    log('ERROR: no model installed')
    return
  }
  engine.start(manifest, dictation.onText, dictation.onSegment)
}

// Failing here used to be silent: the log had the reason and the screen just said "no model".
export async function ensureModel(): Promise<{ error: string | null }> {
  modelError = null
  const swept = models.sweepOrphans()
  if (swept.length) log('models: swept ' + swept.join(', '))
  try {
    await models.ensureDefault(
      APPDATA,
      (p) => {
        downloading = p
        windows.broadcast('models:progress', p)
      },
      (notice) => log('model: ' + notice)
    )
  } catch (err) {
    modelError = (err as Error).message
    log('ERROR ensuring the default model: ' + modelError)
  }
  downloading = null
  windows.broadcast('models:progress', null)
  startEngine()
  return { error: modelError }
}

async function switchModel(id: string): Promise<ModelRow[]> {
  config.update({ model: id })
  await engine.stop()
  startEngine()
  return models.list(config.get().model)
}

export function register(): void {
  handle('config:read', () => config.get())

  handle('config:write', (patch: Partial<Config>) => {
    const before = config.get().key
    const next = config.update(patch)
    if (patch.key && patch.key !== before) dictation.rebindKey()
    return next
  })

  handle('status:read', (): AppStatus => {
    const manifest = activeManifest()
    return {
      engineReady: engine.isReady(),
      hook: native.hookStatus(),
      update: updater.status(),
      modelId: manifest?.id ?? null,
      modelLabel: manifest?.label ?? null,
      downloading,
      modelError,
      version: app.getVersion()
    }
  })

  handle('history:read', (): HistoryEntry[] => {
    try {
      return readFileSync(HISTORY_FILE, 'utf8')
        .trim()
        .split('\n')
        .filter(Boolean)
        .slice(-100)
        .map((l) => JSON.parse(l) as HistoryEntry)
        .toReversed()
    } catch {
      return []
    }
  })

  handle('history:clear', () => {
    try {
      unlinkSync(HISTORY_FILE)
    } catch {
      // Already gone is the same as cleared.
    }
    return true as const
  })

  handle('models:list', () => models.list(config.get().model))

  handle('models:use', async (id: string) => {
    if (!models.isInstalled(id)) throw new Error(t(resolveLang(), 'modelNotDownloaded'))
    return switchModel(id)
  })

  handle('models:download', async (id: string) => {
    if (downloading) throw new Error(t(resolveLang(), 'downloadInProgress'))
    downloading = { id, file: '', done: 0, total: 1 }
    try {
      await models.download(id, (p) => {
        downloading = p
        windows.broadcast('models:progress', p)
      })
      log('model downloaded: ' + id)
      return models.list(config.get().model)
    } finally {
      downloading = null
      windows.broadcast('models:progress', null)
    }
  })

  handle('models:delete', async (id: string) => {
    const remaining = models.remove(id)
    log('model deleted: ' + id)
    if (config.get().model === id) return switchModel(remaining)
    return models.list(config.get().model)
  })

  handle('models:retry', () => ensureModel())

  handle('update:check', () => updater.checkNow())

  handle('i18n:lang', () => resolveLang())

  ipcMain.on('audio:chunk', (_e, data: { samples: Float32Array; sampleRate: number }) => {
    dictation.feedAudio(data.samples, data.sampleRate)
  })

  ipcMain.on('audio:end', () => dictation.endAudio())

  ipcMain.on('renderer-log', (_e, message: string) => log('renderer: ' + message))
}
