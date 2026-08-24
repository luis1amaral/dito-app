// Every window the app owns. One place decides size, flags and how a screen is loaded.
import { BrowserWindow, screen } from 'electron'
import { join } from 'node:path'
import type { EventChannel, EventMap } from '../shared/ipc'
import { asset } from './paths'
import { log } from './logger'

const PRELOAD = join(__dirname, '../preload/index.js')

// electron-vite serves the screens from a dev server while developing and from disk once packaged.
function loadScreen(win: BrowserWindow, name: string): void {
  const devServer = process.env['ELECTRON_RENDERER_URL']
  if (devServer) void win.loadURL(devServer + '/' + name + '.html')
  else void win.loadFile(join(__dirname, '../renderer/' + name + '.html'))
}

let pill: BrowserWindow | null = null
let settings: BrowserWindow | null = null

export function createPill(): void {
  const area = screen.getPrimaryDisplay().workAreaSize
  const width = 440
  const height = 140
  pill = new BrowserWindow({
    width,
    height,
    x: Math.round((area.width - width) / 2),
    y: area.height - height - 20,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: false,
    show: false,
    hasShadow: false,
    backgroundColor: '#00000000',
    webPreferences: { preload: PRELOAD, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false }
  })
  pill.setAlwaysOnTop(true, 'screen-saver')
  // The constructor flag doesn't always stick before the WM maps the window on Linux.
  pill.setSkipTaskbar(true)
  // Click-through: the pill never steals the cursor from whoever is working.
  pill.setIgnoreMouseEvents(true)
  loadScreen(pill, 'pill')
  pill.on('closed', () => {
    pill = null
  })
}

// Re-assert on every show: inside the topmost band, whoever set it last wins.
export function showPill(): void {
  if (!pill) return
  pill.setAlwaysOnTop(true, 'screen-saver')
  pill.showInactive()
  pill.moveTop()
}

export function hidePill(): void {
  pill?.hide()
}

export function openSettings(capture = false): void {
  if (settings) {
    settings.show()
    settings.focus()
    return
  }
  settings = new BrowserWindow({
    width: 1020,
    height: 700,
    minWidth: 880,
    minHeight: 600,
    title: 'Dito',
    icon: asset(process.platform === 'linux' ? 'icon.png' : 'dito.ico'),
    backgroundColor: '#0E0E13',
    autoHideMenuBar: true,
    webPreferences: { preload: PRELOAD, contextIsolation: true, nodeIntegration: false }
  })
  log('settings window created')
  loadScreen(settings, 'settings')
  settings.webContents.on('console-message', (_e, level, message, line, source) => {
    if (level >= 2) log('settings[console] ' + message + ' (' + source + ':' + line + ')')
  })
  if (capture) armCapture(settings)
  settings.on('closed', () => {
    settings = null
  })
}

// --capture: capturePage stalls on a window Chromium is not painting, so show it first.
function armCapture(win: BrowserWindow): void {
  win.webContents.once('did-finish-load', () => {
    log('settings did-finish-load')
    win.show()
    win.focus()
    setTimeout(() => {
      win.webContents
        .capturePage()
        .then(async (img) => {
          const { writeFileSync } = await import('node:fs')
          const { tmpdir } = await import('node:os')
          const file = join(tmpdir(), 'dito_page.png')
          writeFileSync(file, img.toPNG())
          log('captured to ' + file)
        })
        .catch((err: Error) => log('capture FAILED: ' + err.message))
    }, 2500)
  })
}

/** Typed push to one screen; the channel and its payload come from the shared contract. */
export function sendTo<C extends EventChannel>(
  target: 'pill' | 'settings',
  channel: C,
  payload: EventMap[C]
): void {
  const win = target === 'pill' ? pill : settings
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload)
}

export function broadcast<C extends EventChannel>(channel: C, payload: EventMap[C]): void {
  for (const win of [pill, settings]) {
    if (win && !win.isDestroyed()) win.webContents.send(channel, payload)
  }
}

export function settingsOpen(): boolean {
  return settings !== null
}
