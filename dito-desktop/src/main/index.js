// Dito 2.0 -- voice dictation only: press a key, speak, the text is typed where the cursor was.
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage, shell } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { Worker } = require('node:worker_threads')
const models = require('./models')

const ROOT = path.join(__dirname, '..', '..')
const APPDATA = app.getPath('appData')
const DATA_DIR = path.join(APPDATA, 'dito')
const CONFIG_FILE = path.join(DATA_DIR, 'config.json')
const LOG_FILE = path.join(DATA_DIR, 'logs', 'app.log')
const HISTORY_FILE = path.join(DATA_DIR, 'history.jsonl')

fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true })

// Synchronous on purpose: with an async sink the last line is lost in a segfault and the
// diagnosis blames the wrong function -- that already happened and cost a whole session.
function log(msg) {
  const line = new Date().toISOString() + ' ' + msg + '\n'
  try { fs.appendFileSync(LOG_FILE, line) } catch {}
  process.stdout.write(line)
}

const DEFAULTS = { key: 'F9', mode: 'toggle', microphone: null, autoPaste: true, model: models.DEFAULT_MODEL.id }

function readConfig() {
  try {
    return Object.assign({}, DEFAULTS, JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8')))
  } catch {
    return Object.assign({}, DEFAULTS)
  }
}

function writeConfig(c) {
  fs.mkdirSync(DATA_DIR, { recursive: true })
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(c, null, 2))
}

let config = readConfig()

let native = null
try {
  native = require(path.join(ROOT, 'native', 'build', 'Release', 'dito_win32.node'))
} catch (err) {
  log('ERROR loading native addon: ' + err.message)
}

let pill = null
let settings = null
let tray = null
let worker = null
let engineReady = false
let state = 'idle'
let requestId = 0
let downloading = null

function asset(name) {
  return path.join(ROOT, 'assets', name)
}

// ------------------------------------------------------------------ windows --
function createPill() {
  const area = screen.getPrimaryDisplay().workAreaSize
  const W = 440
  const H = 140
  pill = new BrowserWindow({
    width: W,
    height: H,
    x: Math.round((area.width - W) / 2),
    y: area.height - H - 20,
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
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false }
  })
  pill.setAlwaysOnTop(true, 'screen-saver')
  // Click-through: the pill never steals the cursor from whoever is working.
  pill.setIgnoreMouseEvents(true)
  pill.loadFile(path.join(ROOT, 'src', 'renderer', 'pill.html'))
  pill.on('closed', () => { pill = null })
}

function openSettings() {
  if (settings) { settings.show(); settings.focus(); return }
  settings = new BrowserWindow({
    width: 1020,
    height: 700,
    minWidth: 880,
    minHeight: 600,
    title: 'Dito',
    icon: asset('dito.ico'),
    backgroundColor: '#0E0E13',
    autoHideMenuBar: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false }
  })
  log('settings window created')
  settings.loadFile(path.join(ROOT, 'src', 'renderer', 'settings.html'))
  settings.webContents.on('console-message', (_e, level, msg, line, source) => {
    if (level >= 2) log('settings[console] ' + msg + ' (' + source + ':' + line + ')')
  })
  // --capture: Chromium itself reports what it painted. PrintWindow cannot see a GPU surface.
  if (process.argv.includes('--capture')) {
    settings.webContents.once('did-finish-load', () => {
      log('settings did-finish-load')
      // capturePage stalls on a window Chromium is not painting: show and focus it first.
      settings.show()
      settings.focus()
      setTimeout(() => {
        settings.webContents.capturePage()
          .then((img) => {
            const file = path.join(os.tmpdir(), 'dito_page.png')
            fs.writeFileSync(file, img.toPNG())
            log('captured to ' + file)
          })
          .catch((err) => log('capture FAILED: ' + err.message))
      }, 2500)
    })
  }
  settings.on('closed', () => { settings = null })
}

// State icons reused from the Flutter app (assets/icons/tray-*.ico).
function trayIcon(phase) {
  const name = phase === 'recording' ? 'tray-recording.ico' : phase === 'error' ? 'tray-alert.ico' : 'tray-idle.ico'
  const file = asset(name)
  return fs.existsSync(file) ? nativeImage.createFromPath(file) : nativeImage.createEmpty()
}

function createTray() {
  tray = new Tray(trayIcon('idle'))
  tray.setToolTip('Dito - ditado por voz')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Abrir Dito', click: openSettings },
    { label: 'Pasta de dados', click: () => shell.openPath(DATA_DIR) },
    { type: 'separator' },
    { label: 'Sair', click: () => { app.isQuitting = true; app.quit() } }
  ]))
  tray.on('click', openSettings)
  tray.on('double-click', openSettings)
}

function notifyWindows(channel, payload) {
  for (const w of [settings, pill]) {
    if (w && !w.isDestroyed()) w.webContents.send(channel, payload)
  }
}

// ------------------------------------------------------------------- engine --
function activeModel() {
  if (models.isInstalled(APPDATA, config.model)) return models.CATALOG.find((m) => m.id === config.model)
  return models.CATALOG.find((m) => models.isInstalled(APPDATA, m.id)) || null
}

function activeModelDir() {
  const m = activeModel()
  return m ? models.dirFor(APPDATA, m.id) : null
}

function startEngine() {
  const modelDir = activeModelDir()
  if (!modelDir) {
    log('ERROR: no model installed')
    return
  }
  engineReady = false
  log('engine: model at ' + modelDir)
  const manifest = activeModel()
  worker = new Worker(path.join(__dirname, 'engine-worker.js'), {
    workerData: {
      modelDir,
      sherpaPath: require.resolve('sherpa-onnx-node'),
      manifest: { id: manifest.id, type: manifest.type, streaming: manifest.streaming, modelingUnit: manifest.modelingUnit }
    }
  })
  worker.on('message', (m) => {
    if (m.kind === 'ready') {
      engineReady = true
      log('engine: ready in ' + m.ms + ' ms')
      log('boot completo')
    } else if (m.kind === 'error') {
      log('engine: FAILED - ' + m.error)
    } else if (m.kind === 'text') {
      onTranscribed(m)
    }
  })
  worker.on('error', (e) => log('engine: thread error - ' + e.message))
}

async function switchModel(id) {
  config.model = id
  writeConfig(config)
  if (worker) { await worker.terminate(); worker = null }
  startEngine()
}

function onTranscribed(m) {
  const text = (m.text || '').trim()
  const speed = m.seconds ? (m.seconds / (m.ms / 1000)).toFixed(1) : '?'
  log('transcribed: ' + m.ms + ' ms (' + speed + 'x) "' + text + '"')
  if (!text) {
    showPill('error', 'não entendi')
    setTimeout(hidePill, 1600)
    state = 'idle'
    return
  }
  try {
    fs.appendFileSync(HISTORY_FILE, JSON.stringify({ at: new Date().toISOString(), text }) + '\n')
  } catch {}

  let pasted = false
  if (config.autoPaste && native) {
    const target = native.currentTarget()
    pasted = native.paste(text)
    log('paste: ' + pasted + ' into ' + target.kind + ' "' + target.title + '"')
  }
  showPill(pasted ? 'pasted' : 'done', text)
  setTimeout(hidePill, 2000)
  state = 'idle'
}

// --------------------------------------------------------------------- pill --
function showPill(phase, detail) {
  if (tray) tray.setImage(trayIcon(phase))
  if (!pill) return
  pill.showInactive()
  pill.webContents.send('state', { phase, detail })
}

function hidePill() {
  if (tray) tray.setImage(trayIcon('idle'))
  if (!pill) return
  pill.webContents.send('state', { phase: 'idle', detail: '' })
  // Wait for the exit animation before the window disappears.
  setTimeout(() => { if (pill && state === 'idle') pill.hide() }, 240)
}

// --------------------------------------------------------------------- flow --
function startDictation() {
  if (state !== 'idle') return
  if (!engineReady) {
    showPill('error', 'o motor ainda está carregando')
    setTimeout(hidePill, 1600)
    return
  }
  state = 'recording'
  showPill('recording', '')
  pill.webContents.send('record', { microphone: config.microphone })
  log('dictation: started')
}

function stopDictation() {
  if (state !== 'recording') return
  state = 'transcribing'
  showPill('transcribing', '')
  pill.webContents.send('stop')
  log('dictation: stopped, transcribing')
}

function bindKey() {
  if (!native) return
  let lastDown = 0
  const ok = native.startHook(config.key, (e) => {
    if (e.kind !== 'edge' || e.action !== 'dictation') return
    if (config.mode === 'hold') {
      if (e.down) startDictation()
      else stopDictation()
      return
    }
    // Toggle: only the key-down counts; key-up is ignored on purpose.
    if (!e.down) return
    const now = Date.now()
    if (now - lastDown < 250) return
    lastDown = now
    if (state === 'recording') stopDictation()
    else startDictation()
  })
  const st = native.hookStatus()
  log('key: ' + config.key + ' mode=' + config.mode + ' bound=' + ok + ' installed=' + st.installed + ' error=' + st.error)
}

// ---------------------------------------------------------------------- IPC --
ipcMain.on('audio', (_e, data) => {
  if (!worker) return
  requestId += 1
  worker.postMessage({ kind: 'transcribe', id: requestId, samples: data.samples, sampleRate: data.sampleRate })
})

ipcMain.handle('config:read', () => config)

ipcMain.handle('config:write', (_e, next) => {
  const keyChanged = next.key && next.key !== config.key
  config = Object.assign({}, config, next)
  writeConfig(config)
  if (keyChanged && native) { native.stopHook(); bindKey() }
  log('config: ' + JSON.stringify(config))
  return config
})

ipcMain.handle('history:read', () => {
  try {
    return fs.readFileSync(HISTORY_FILE, 'utf8').trim().split('\n').filter(Boolean)
      .slice(-100).map((l) => JSON.parse(l)).reverse()
  } catch {
    return []
  }
})

ipcMain.handle('history:clear', () => {
  try { fs.unlinkSync(HISTORY_FILE) } catch {}
  return true
})

ipcMain.handle('status:read', () => {
  const st = native ? native.hookStatus() : { installed: false, error: -1 }
  return { engineReady, hook: st, modelDir: activeModelDir(), downloading, version: app.getVersion() }
})

ipcMain.handle('models:list', () => models.list(APPDATA, config.model))

ipcMain.handle('models:use', async (_e, id) => {
  if (!models.isInstalled(APPDATA, id)) throw new Error('esse modelo ainda não foi baixado')
  await switchModel(id)
  return models.list(APPDATA, config.model)
})

ipcMain.handle('models:download', async (_e, id) => {
  if (downloading) throw new Error('já existe um download em andamento')
  downloading = { id, done: 0, total: 1 }
  try {
    await models.download(APPDATA, id, (p) => {
      downloading = p
      notifyWindows('models:progress', p)
    })
    log('model downloaded: ' + id)
    return models.list(APPDATA, config.model)
  } finally {
    downloading = null
    notifyWindows('models:progress', null)
  }
})

ipcMain.handle('models:delete', async (_e, id) => {
  const remaining = models.remove(APPDATA, id)
  log('model deleted: ' + id)
  if (config.model === id) await switchModel(remaining)
  return models.list(APPDATA, config.model)
})

ipcMain.on('renderer-log', (_e, m) => log('renderer: ' + m))

// --------------------------------------------------------------------- life --
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', openSettings)

  app.whenReady().then(async () => {
    log('dito ' + app.getVersion() + ' starting · pid ' + process.pid + ' · electron ' + process.versions.electron + ' · argv ' + JSON.stringify(process.argv.slice(1)))
    createPill()
    createTray()
    bindKey()
    // Always starts in the tray: opening a window unasked is bad usability (owner's call).
    // The window shows on tray click, on a second launch, or with --capture for the smoke gate.
    if (process.argv.includes('--capture')) openSettings()

    try {
      await models.ensureDefault(APPDATA, (p) => {
        downloading = p
        notifyWindows('models:progress', p)
      }, (notice) => log('model: ' + notice))
    } catch (err) {
      log('ERROR ensuring the default model: ' + err.message)
    }
    downloading = null
    notifyWindows('models:progress', null)
    startEngine()
  })

  // Closing the window does not quit: the app lives in the tray.
  app.on('window-all-closed', () => {})
  app.on('before-quit', () => { if (native) native.stopHook() })
}
