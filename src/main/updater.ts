// Auto-update with backoff on a failing feed; why in docs/decisoes.md.
import type { AppUpdater } from 'electron-updater'
import type { UpdateState } from '../shared/ipc'
import { log } from './logger'

const FIRST_CHECK_MS = 20_000
const BASE_INTERVAL_MS = 6 * 60 * 60 * 1000
const MAX_INTERVAL_MS = 24 * 60 * 60 * 1000

let updater: AppUpdater | null = null
let failures = 0
let timer: NodeJS.Timeout | null = null
let state: UpdateState = { state: 'idle', text: 'nunca verificado' }

function load(): AppUpdater | null {
  if (updater) return updater
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    updater = (require('electron-updater') as { autoUpdater: AppUpdater }).autoUpdater
  } catch (err) {
    log('updater: indisponivel - ' + (err as Error).message)
    return null
  }
  // Never surprise the user mid-dictation: download in background, install on quit.
  updater.autoDownload = true
  updater.autoInstallOnAppQuit = true
  updater.on('update-available', (i: { version: string }) => {
    state = { state: 'downloading', text: 'versão ' + i.version + ' disponível, baixando…' }
    log('updater: disponivel ' + i.version)
  })
  updater.on('update-not-available', () => {
    state = { state: 'ok', text: 'você já está na última versão' }
    log('updater: ja esta na ultima')
  })
  updater.on('update-downloaded', (i: { version: string }) => {
    state = { state: 'ready', text: 'versão ' + i.version + ' pronta — será instalada ao sair' }
    log('updater: ' + i.version + ' baixada, instala ao sair')
  })
  updater.on('error', (e: Error) => {
    state = { state: 'error', text: e.message }
    log('updater: erro - ' + e.message)
  })
  return updater
}

export async function checkNow(): Promise<UpdateState> {
  const u = load()
  if (!u) {
    state = { state: 'error', text: 'auto-update indisponível nesta build' }
    return state
  }
  state = { state: 'checking', text: 'procurando…' }
  try {
    const r = await u.checkForUpdates()
    failures = 0
    log('updater: checou · feed em ' + (r?.updateInfo?.version ?? '?'))
  } catch (err) {
    failures += 1
    state = { state: 'error', text: (err as Error).message }
    log('updater: falhou (' + failures + ') - ' + (err as Error).message)
  }
  return state
}

function schedule(ms: number): void {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    void checkNow().then(() => schedule(Math.min(BASE_INTERVAL_MS * 2 ** failures, MAX_INTERVAL_MS)))
  }, ms)
  timer.unref?.()
}

// Only a packaged build has a feed to talk to; in dev the button says so plainly.
export function start(packaged: boolean): void {
  if (!packaged) {
    state = { state: 'idle', text: 'auto-update só funciona no app instalado' }
    log('updater: em desenvolvimento, sem verificacao automatica')
    return
  }
  schedule(FIRST_CHECK_MS)
}

export function status(): UpdateState {
  return state
}
