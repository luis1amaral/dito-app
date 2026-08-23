// End-to-end proof for HOLD mode: nobody measured it before, only the toggle path had a gate.
// Down must start, up must stop, five cycles in a row must all work, and a swallowed key-up
// must self-heal from the native watchdog timer instead of leaving dictation stuck on.
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const EXE = process.argv[2] || path.join(HERE, '..', 'dist', 'win-unpacked', 'Dito.exe')
const LOG = path.join(process.env.APPDATA, 'dito', 'logs', 'app.log')
const CONFIG = path.join(process.env.APPDATA, 'dito', 'config.json')

const VK = { F8: 0x77, F9: 0x78, F10: 0x79, F11: 0x7a, F12: 0x7b, ScrollLock: 0x91, Pause: 0x13 }

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const ps = (cmd) => execFileSync('powershell', ['-NoProfile', '-Command', cmd], { encoding: 'utf8' })

if (!fs.existsSync(EXE)) {
  console.log('HOLD: PENDENTE - nao existe binario em ' + EXE)
  process.exit(2)
}

let originalConfig = null
try { originalConfig = fs.readFileSync(CONFIG, 'utf8') } catch {}

function restoreConfig() {
  try {
    if (originalConfig !== null) fs.writeFileSync(CONFIG, originalConfig)
  } catch {}
}

let cfg = {}
try { cfg = JSON.parse(originalConfig || '{}') } catch {}
const key = cfg.key || 'F9'
const vk = VK[key]
if (!vk) {
  console.error('HOLD: FALHA - tecla desconhecida na config: ' + key)
  process.exit(1)
}

try {
  fs.mkdirSync(path.dirname(CONFIG), { recursive: true })
  fs.writeFileSync(CONFIG, JSON.stringify({ ...cfg, mode: 'hold' }, null, 2))
} catch (err) {
  console.error('HOLD: FALHA - nao consegui escrever a config: ' + err.message)
  process.exit(1)
}

const SEND_INPUT = `
Add-Type @'
using System; using System.Runtime.InteropServices;
public class K {
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public KEYBDINPUT ki; public int pad1; public int pad2; }
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] i, int cb);
  public static void Send(ushort vk, uint flags) {
    INPUT[] a = new INPUT[1];
    a[0].type = 1; a[0].ki.wVk = vk; a[0].ki.dwFlags = flags;
    SendInput(1, a, Marshal.SizeOf(typeof(INPUT)));
  }
}
'@
[K]::Send(VKHERE, FLAGSHERE)
`

function keyDown() {
  ps(SEND_INPUT.replace('VKHERE', String(vk)).replace('FLAGSHERE', '0'))
}

function keyUp() {
  ps(SEND_INPUT.replace('VKHERE', String(vk)).replace('FLAGSHERE', '2'))
}

function logSince(pid) {
  let lines = []
  try { lines = fs.readFileSync(LOG, 'utf8').split('\n') } catch {}
  const mark = 'pid ' + pid + ' '
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (lines[i].includes('starting') && lines[i].includes(mark)) return lines.slice(i)
  }
  return []
}

function countMatches(pid, needle) {
  return logSince(pid).filter((l) => l.includes(needle)).length
}

// Counts a fresh occurrence, not "does it exist anywhere" -- started/stopped repeat across
// cycles, and a stale line from an earlier cycle would pass the check before anything happened.
async function waitForNext(pid, needle, seconds, baseline) {
  for (let i = 0; i < seconds * 4; i += 1) {
    if (countMatches(pid, needle) > baseline) return true
    await wait(250)
  }
  return false
}

try { ps("Get-Process Dito, electron -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; exit 0") } catch {}
await wait(1500)

// A short cap makes the last-resort stop testable; production keeps the 180 s default.
// Killing by pid leaves child processes dying; the next gate then hits the single-instance lock.
async function waitForCleanSlate() {
  for (let i = 0; i < 40; i += 1) {
    const alive = Number(ps('@(Get-Process Dito, electron -ErrorAction SilentlyContinue).Count').trim())
    if (!alive) return true
    try { ps('Get-Process Dito, electron -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; exit 0') } catch {}
    await wait(250)
  }
  return false
}

if (!(await waitForCleanSlate())) {
  console.error("PENDENTE - sobrou instancia viva; a medida seria de outro processo")
  process.exit(2)
}

const pid = Number(ps(`$env:DITO_MAX_HOLD_MS='2500'; (Start-Process '${EXE}' -PassThru).Id`).trim())
console.log('app subiu: pid ' + pid + ' · tecla ' + key + ' · modo hold')

function finish(code, msg) {
  try { execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
  restoreConfig()
  if (msg) console.error(msg)
  process.exit(code)
}

if (!(await waitForNext(pid, 'boot completo', 60, 0))) finish(1, 'HOLD: FALHA - o app nao terminou de subir')

const bound = logSince(pid).find((l) => l.includes('key: '))
console.log('   ' + (bound || 'sem linha de tecla no log').trim().replace(/^\S+\s/, ''))
if (!bound || !bound.includes('installed=true') || !bound.includes('mode=hold')) {
  finish(1, 'HOLD: FALHA - o hook nao instalou em modo hold')
}

// Test A: hold and release
console.log('-- teste A: segurar e soltar')
let base = countMatches(pid, 'dictation: started')
keyDown()
if (!(await waitForNext(pid, 'dictation: started', 8, base))) {
  finish(1, 'HOLD: FALHA - segurei ' + key + ' e o ditado NAO comecou')
}
console.log('   down -> ditado comecou: OK')
await wait(1500)
base = countMatches(pid, 'dictation: stopped')
keyUp()
if (!(await waitForNext(pid, 'dictation: stopped', 8, base))) {
  finish(1, 'HOLD: FALHA - soltei ' + key + ' e o ditado NAO parou')
}
console.log('   up -> ditado parou: OK')

// Test B: five cycles, the key that works once and goes mute is the real trap
console.log('-- teste B: 5 ciclos seguidos')
for (let i = 1; i <= 5; i += 1) {
  base = countMatches(pid, 'dictation: started')
  keyDown()
  if (!(await waitForNext(pid, 'dictation: started', 8, base))) {
    finish(1, 'HOLD: FALHA - ciclo ' + i + '/5: down nao iniciou o ditado')
  }
  await wait(600)
  base = countMatches(pid, 'dictation: stopped')
  keyUp()
  if (!(await waitForNext(pid, 'dictation: stopped', 8, base))) {
    finish(1, 'HOLD: FALHA - ciclo ' + i + '/5: up nao parou o ditado')
  }
  console.log('   ciclo ' + i + '/5: OK')
}

// Test C: a swallowed key-up must not leave dictation stuck -- the watchdog timer has to catch it
console.log('-- teste C: teto de duracao')
base = countMatches(pid, 'dictation: started')
keyDown()
if (!(await waitForNext(pid, 'dictation: started', 8, base))) {
  finish(1, 'HOLD: FALHA - down nao iniciou o ditado antes do teste de key-up engolido')
}
console.log('   down -> ditado comecou: OK (up NAO sera enviado; espera o teto)')
base = countMatches(pid, 'dictation: stopped')
if (!(await waitForNext(pid, 'dictation: stopped', 3, base))) {
  finish(1, 'HOLD: FALHA - o teto de duracao nao encerrou o ditado; ele ficaria preso ligado')
}
console.log('   watchdog percebeu a tecla fisicamente solta e parou sozinho: OK')

console.log('HOLD: PASSA - segurar/soltar, 5 ciclos e key-up engolido todos provados')
finish(0)
