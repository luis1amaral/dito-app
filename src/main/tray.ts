// Tray icon and menu. State icons reused from the Flutter app (assets/icons/tray-*.ico).
import { Menu, Tray, app, nativeImage, shell } from 'electron'
import { existsSync } from 'node:fs'
import type { DictationPhase } from '../shared/ipc'
import { DATA_DIR, asset } from './paths'
import { openSettings } from './windows'

let tray: Tray | null = null

function icon(phase: DictationPhase): Electron.NativeImage {
  const state = phase === 'recording' ? 'tray-recording' : phase === 'error' ? 'tray-alert' : 'tray-idle'
  const ext = process.platform === 'linux' ? '.png' : '.ico'
  const file = asset(state + ext)
  return existsSync(file) ? nativeImage.createFromPath(file) : nativeImage.createEmpty()
}

export function create(): void {
  tray = new Tray(icon('idle'))
  tray.setToolTip('Dito - ditado por voz')
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Abrir Dito', click: () => openSettings() },
      { label: 'Pasta de dados', click: () => void shell.openPath(DATA_DIR) },
      { type: 'separator' },
      {
        label: 'Sair',
        click: () => {
          app.quit()
        }
      }
    ])
  )
  tray.on('click', () => openSettings())
  tray.on('double-click', () => openSettings())
}

export function setPhase(phase: DictationPhase): void {
  tray?.setImage(icon(phase))
}
