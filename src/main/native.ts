// Optional at load time: without it the app still opens and says what is wrong.
import { clipboard } from 'electron'
import type { HookStatus } from '../shared/ipc'
import { addonPath } from './paths'
import { log } from './logger'

export type TargetInfo = { hwnd: number; className: string; title: string; kind: string }

export type KeyEdge = { kind: 'edge' | 'tick' | 'status'; action: string; key: string; down: boolean }

type Addon = {
  /** The action name lives in the addon; JS must never repeat the literal. */
  ACTION: string
  startHook(key: string, onEdge: (edge: KeyEdge) => void): boolean
  stopHook(): void
  hookStatus(): HookStatus
  rememberTarget(): void
  currentTarget(): TargetInfo
  targetIsForeground(): boolean
  paste(text: string): boolean
  typeText(text: string): boolean
  sendEnter(): boolean
}

let addon: Addon | null = null

try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  addon = require(addonPath()) as Addon
} catch (err) {
  log('ERROR loading native addon: ' + (err as Error).message)
}

export function available(): boolean {
  return addon !== null
}

export function action(): string {
  return addon ? addon.ACTION : ''
}

export function startHook(key: string, onEdge: (edge: KeyEdge) => void): boolean {
  return addon ? addon.startHook(key, onEdge) : false
}

export function stopHook(): void {
  addon?.stopHook()
}

export function hookStatus(): HookStatus {
  return addon ? addon.hookStatus() : { installed: false, error: -1, seen: 0, pumps: 0 }
}

export function currentTarget(): TargetInfo {
  return addon ? addon.currentTarget() : { hwnd: 0, className: '', title: '', kind: 'gui' }
}

export function targetIsForeground(): boolean {
  return addon ? addon.targetIsForeground() : false
}

// X11 has no clipboard API in the addon on purpose: Electron already owns the selection.
export function paste(text: string): boolean {
  if (!addon) return false
  if (process.platform === 'linux') clipboard.writeText(text)
  return addon.paste(text)
}

export function typeText(text: string): boolean {
  return addon ? addon.typeText(text) : false
}

export function sendEnter(): boolean {
  return addon ? addon.sendEnter() : false
}
