// Every path the app writes to, declared once.
import { app } from 'electron'
import { join } from 'node:path'

// The override lets a gate import this module outside Electron, where app is undefined.
export const APPDATA = process.env['DITO_APPDATA'] ?? app.getPath('appData')
export const DATA_DIR = join(APPDATA, 'dito')
export const CONFIG_FILE = join(DATA_DIR, 'config.json')
export const LOG_FILE = join(DATA_DIR, 'logs', 'app.log')
export const HISTORY_FILE = join(DATA_DIR, 'history.jsonl')
export const MODELS_DIR = join(DATA_DIR, 'speech-models')

/** Files shipped with the app: icons and the native addon. */
export function asset(name: string): string {
  return join(app.getAppPath(), 'assets', name)
}

export function addonPath(): string {
  // Unpacked from the asar by electron-builder; the loader needs a real path on disk.
  return join(app.getAppPath().replace('app.asar', 'app.asar.unpacked'), 'native', 'build', 'Release', 'dito_win32.node')
}
