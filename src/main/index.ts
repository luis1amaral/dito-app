// Startup only: everything else lives in its own module.
import { app } from 'electron'
import * as dictation from './dictation'
import * as ipc from './ipc'
import * as native from './native'
import * as tray from './tray'
import * as updater from './updater'
import * as windows from './windows'
import { log } from './logger'

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => windows.openSettings())

  // A dead renderer or GPU process used to leave no trace: the pill just stopped working.
  app.on('render-process-gone', (_e, _contents, details) => {
    log('CRASH renderer: ' + details.reason + ' (exit ' + details.exitCode + ')')
  })
  app.on('child-process-gone', (_e, details) => {
    log('CRASH ' + details.type + ': ' + details.reason + ' (exit ' + details.exitCode + ')')
  })
  process.on('uncaughtException', (err) => log('CRASH main: ' + (err.stack ?? err.message)))
  process.on('unhandledRejection', (err) => log('CRASH promise: ' + String(err)))

  void app.whenReady().then(async () => {
    log(
      'dito ' + app.getVersion() + ' starting · pid ' + process.pid +
        ' · electron ' + process.versions.electron +
        ' · argv ' + JSON.stringify(process.argv.slice(1))
    )
    ipc.register()
    windows.createPill()
    tray.create()
    dictation.bindKey()
    // Always starts in the tray; the window opens on tray click or with --capture.
    if (process.argv.includes('--capture')) windows.openSettings(true)

    await ipc.ensureModel()
    updater.start(app.isPackaged)
  })

  // Closing the window does not quit: the app lives in the tray.
  app.on('window-all-closed', () => {})
  app.on('before-quit', () => native.stopHook())
}
