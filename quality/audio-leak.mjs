// Gate: cancelling a take must leave NOTHING capturing. This is the defect fixed in 2.0.16 --
// stopping while getUserMedia was still pending left the microphone recording in the background.
// Runs headless on Windows and on Linux: the proof is the track state, not the OS audio server.
import { app, BrowserWindow } from 'electron'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = join(import.meta.dirname, '..')
const PILL = join(ROOT, 'out', 'renderer', 'pill.html')
const PRELOAD = join(import.meta.dirname, 'audio-leak-preload.js')
// Three windows around the async getUserMedia, and one stop that arrives BEFORE the phase message:
// that last one is the whole reason the session token exists, since the phase still reads recording.
const SCENARIOS = [
  { race: 0, phaseFirst: true },
  { race: 60, phaseFirst: true },
  { race: 250, phaseFirst: true },
  { race: 0, phaseFirst: false }
]
const SETTLE_MS = 1200

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

app.commandLine.appendSwitch('use-fake-device-for-media-stream')
app.commandLine.appendSwitch('use-fake-ui-for-media-stream')
app.commandLine.appendSwitch('no-sandbox')

if (!existsSync(PILL)) {
  console.error('LEAK: FALHA - ' + PILL + ' nao existe; rode "npm run build" antes')
  process.exit(1)
}

app.on('ready', async () => {
  let failures = 0
  const win = new BrowserWindow({
    show: false,
    webPreferences: { preload: PRELOAD, contextIsolation: false, sandbox: false },
  })
  win.webContents.session.setPermissionRequestHandler((_wc, _p, done) => done(true))

  try {
    await win.loadFile(PILL)

    for (const { race, phaseFirst } of SCENARIOS) {
      const before = await win.webContents.executeJavaScript('window.gateHooks.report()')
      await win.webContents.executeJavaScript(`
        window.gateHooks.emit('state', { phase: 'recording', detail: '' })
        window.gateHooks.emit('record', { microphone: null, desktopSourceId: null })
      `)
      await sleep(race)
      // What dictation.stop() does: phase first, then the stop message -- unless we race it.
      await win.webContents.executeJavaScript(`
        ${phaseFirst ? "window.gateHooks.emit('state', { phase: 'transcribing', detail: '' })" : ''}
        window.gateHooks.emit('stop')
      `)
      // Snapshot right after the stop: any audio sent from here on is background noise.
      const atStop = await win.webContents.executeJavaScript('window.gateHooks.report()')
      await sleep(SETTLE_MS)

      const after = await win.webContents.executeJavaScript('window.gateHooks.report()')
      const got = after.acquired - before.acquired
      const late = after.sent.slice(atStop.sent.length).filter((c) => c === 'audio:chunk').length
      const how = phaseFirst ? 'fase+stop' : 'só stop'
      console.log(`-- ${how.padEnd(9)} em ${String(race).padStart(3)} ms · streams pegos ${got} · tracks vivos ${after.live} · audio depois de parar ${late}`)
      if (late > 0) {
        console.log('   REPROVA: o renderer seguiu enviando audio depois do stop')
        failures += 1
      }
      if (got === 0) {
        console.log('   REPROVA: nenhum getUserMedia aconteceu — o teste passaria sem provar nada')
        failures += 1
      }
      if (after.live > 0) {
        console.log('   REPROVA: sobrou captura viva depois de parar (audio de fundo seguiria sendo gravado)')
        failures += 1
      }
    }

    const final = await win.webContents.executeJavaScript('window.gateHooks.report()')
    console.log(`LEAK: ${final.acquired} stream(s) no total, ${final.tracks} track(s), ${final.live} vivo(s) no fim`)
  } catch (err) {
    console.error('LEAK: FALHA - ' + err.message)
    failures += 1
  }

  if (failures) {
    console.log('LEAK: FALHA')
    // app.exit only schedules the quit, so without returning the success line would still print.
    app.exit(1)
    return
  }
  console.log('LEAK: PASSA - nenhuma captura sobreviveu ao cancelamento em ' + SCENARIOS.length + ' cenarios')
  app.exit(0)
})
