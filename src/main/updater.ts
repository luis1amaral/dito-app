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
let state: UpdateState = { state: 'idle', text: 'nunca verificado', percent: 0, version: null }

// The lib's raw HTTP dump belongs in the log, never on a settings screen.
export function humanError(err: Error): string {
  const message = err.message ?? ''
  // electron-updater puts the HTTP status first, so the code is the only part worth showing.
  const http = /^\s*(\d{3})\b/.exec(message)
  if (http) return 'o servidor de atualização não respondeu com a versão (código ' + http[1] + ')'
  if (/Cannot find channel|CHANNEL_FILE_NOT_FOUND/i.test(message))
    return 'a versão publicada está sem o manifesto — avise o desenvolvedor'
  if (/ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENETUNREACH|socket hang up/i.test(message))
    return 'não consegui falar com o servidor de atualização'
  return 'não consegui verificar agora — o detalhe está no log'
}

function load(): AppUpdater | null {
  if (updater) return updater
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    updater = (require('electron-updater') as { autoUpdater: AppUpdater }).autoUpdater
  } catch (err) {
    log('updater: indisponivel - ' + (err as Error).message)
    return null
  }
  // Never surprise the user mid-dictation: download in background, install only when asked.
  updater.autoDownload = true
  // Installing on quit swapped the app in silence and never reopened it: it just vanished.
  updater.autoInstallOnAppQuit = false
  updater.on('update-available', (i: { version: string }) => {
    state = { state: 'downloading', text: 'baixando a ' + i.version + '…', percent: 0, version: i.version }
    log('updater: disponivel ' + i.version)
  })
  updater.on('download-progress', (p: { percent: number }) => {
    const percent = Math.max(0, Math.min(100, Math.round(p.percent)))
    state = { ...state, state: 'downloading', percent, text: 'baixando a ' + (state.version ?? '') + '… ' + percent + '%' }
  })
  updater.on('update-not-available', () => {
    state = { state: 'ok', text: 'você já está na última versão', percent: 0, version: null }
    log('updater: ja esta na ultima')
  })
  updater.on('update-downloaded', (i: { version: string }) => {
    state = { state: 'ready', text: 'versão ' + i.version + ' pronta', percent: 100, version: i.version }
    log('updater: ' + i.version + ' baixada, pronta para instalar')
  })
  updater.on('error', (e: Error) => {
    state = { ...state, state: 'error', text: humanError(e) }
    log('updater: erro - ' + e.message)
  })
  return updater
}

export async function checkNow(): Promise<UpdateState> {
  const u = load()
  if (!u) {
    state = { state: 'error', text: 'auto-update indisponível nesta build', percent: 0, version: null }
    return state
  }
  // A finished download must not be thrown away by a new check: it is one click from installing.
  if (state.state === 'ready') return state
  state = { state: 'checking', text: 'procurando…', percent: 0, version: null }
  try {
    const r = await u.checkForUpdates()
    failures = 0
    log('updater: checou · feed em ' + (r?.updateInfo?.version ?? '?'))
  } catch (err) {
    failures += 1
    state = { state: 'error', text: humanError(err as Error), percent: 0, version: null }
    log('updater: falhou (' + failures + ') - ' + (err as Error).message)
  }
  return state
}

// Quits and reopens itself; why install-on-quit was dropped is in docs/decisoes.md.
export function installNow(): UpdateState {
  const u = load()
  if (!u || state.state !== 'ready') {
    log('updater: instalar pedido fora de hora (estado ' + state.state + ')')
    return state
  }
  state = { ...state, state: 'installing', text: 'atualizando… o app vai fechar e reabrir sozinho' }
  log('updater: instalando ' + state.version + ' e relancando')
  // Deferred so this IPC call answers first; the screen would otherwise die mid-reply.
  setTimeout(() => {
    try {
      u.quitAndInstall(true, true)
    } catch (err) {
      state = { ...state, state: 'error', text: humanError(err as Error) }
      log('updater: quitAndInstall falhou - ' + (err as Error).message)
    }
  }, 400)
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
    state = { state: 'idle', text: 'auto-update só funciona no app instalado', percent: 0, version: null }
    log('updater: em desenvolvimento, sem verificacao automatica')
    return
  }
  schedule(FIRST_CHECK_MS)
}

export function status(): UpdateState {
  return state
}
