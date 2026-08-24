// Every path the app writes to, declared once.
import { app } from 'electron'
import { join } from 'node:path'
import { homedir } from 'node:os'

// Override for gates outside Electron; || not ?? because an empty value must not win. Set, it
// wins for every directory below, so gates never scatter files across two locations.
const override = process.env['DITO_APPDATA']
export const APPDATA = override || app.getPath('appData')

const legacyDir = join(APPDATA, 'dito')

// Linux splits data/state per the XDG base dir spec instead of dumping gigabytes of speech
// model into ~/.config; Electron already resolves appData to $XDG_CONFIG_HOME there, so config
// keeps riding legacyDir unchanged.
const useXdg = !override && process.platform === 'linux'
function xdgDir(envVar: string, ...fallback: string[]): string {
  return join(process.env[envVar] || join(homedir(), ...fallback), 'dito')
}

const dataDir = useXdg ? xdgDir('XDG_DATA_HOME', '.local', 'share') : legacyDir
const stateDir = useXdg ? xdgDir('XDG_STATE_HOME', '.local', 'state') : legacyDir

export const DATA_DIR = dataDir
export const CONFIG_FILE = join(legacyDir, 'config.json')
export const LOG_FILE = join(stateDir, 'logs', 'app.log')
export const HISTORY_FILE = join(dataDir, 'history.jsonl')
export const MODELS_DIR = join(dataDir, 'speech-models')

/** Files shipped with the app: icons and the native addon. */
export function asset(name: string): string {
  return join(app.getAppPath(), 'assets', name)
}

export function addonPath(): string {
  // Unpacked from the asar by electron-builder; the loader needs a real path on disk.
  const file = process.platform === 'linux' ? 'dito_linux.node' : 'dito_win32.node'
  return join(app.getAppPath().replace('app.asar', 'app.asar.unpacked'), 'native', 'build', 'Release', file)
}
