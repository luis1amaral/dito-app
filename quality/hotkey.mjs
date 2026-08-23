// End-to-end proof that pressing the key starts and stops a dictation.
// This gate exists because 2.0.0 shipped with the addon emitting "ditado" while the main process
// filtered for "dictation": every key event was dropped and no other layer noticed.
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
  console.log('HOTKEY: PENDENTE - nao existe binario em ' + EXE)
  process.exit(2)
}

let key = 'F9'
try { key = JSON.parse(fs.readFileSync(CONFIG, 'utf8')).key || 'F9' } catch {}
const vk = VK[key]
if (!vk) {
  console.error('HOTKEY: FALHA - tecla desconhecida na config: ' + key)
  process.exit(1)
}

const SEND_INPUT = `
Add-Type @'
using System; using System.Runtime.InteropServices;
public class K {
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public KEYBDINPUT ki; public int pad1; public int pad2; }
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] i, int cb);
  public static void Tap(ushort vk) {
    INPUT[] a = new INPUT[1];
    a[0].type = 1; a[0].ki.wVk = vk; a[0].ki.dwFlags = 0;
    SendInput(1, a, Marshal.SizeOf(typeof(INPUT)));
    System.Threading.Thread.Sleep(60);
    a[0].ki.dwFlags = 2;
    SendInput(1, a, Marshal.SizeOf(typeof(INPUT)));
  }
}
'@
[K]::Tap(VKHERE)
`

function tapKey() {
  ps(SEND_INPUT.replace('VKHERE', String(vk)))
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

async function waitFor(pid, needle, seconds) {
  for (let i = 0; i < seconds * 4; i += 1) {
    if (logSince(pid).some((l) => l.includes(needle))) return true
    await wait(250)
  }
  return false
}

try { ps("Get-Process Dito, electron -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; exit 0") } catch {}
await wait(1500)

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

const pid = Number(ps(`(Start-Process '${EXE}' -PassThru).Id`).trim())
console.log('app subiu: pid ' + pid + ' · tecla ' + key)

function finish(code, msg) {
  try { execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
  if (msg) console.error(msg)
  process.exit(code)
}

if (!(await waitFor(pid, 'boot completo', 60))) finish(1, 'HOTKEY: FALHA - o app nao terminou de subir')

const bound = logSince(pid).find((l) => l.includes('key: '))
console.log('   ' + (bound || 'sem linha de tecla no log').trim().replace(/^\S+\s/, ''))
if (!bound || !bound.includes('installed=true')) finish(1, 'HOTKEY: FALHA - o hook nao instalou')

tapKey()
if (!(await waitFor(pid, 'dictation: started', 8))) {
  finish(1, 'HOTKEY: FALHA - apertei ' + key + ' e o ditado NAO comecou (o evento nao chegou ao app)')
}
console.log('   ' + key + ' -> ditado comecou: OK')

await wait(1200)
tapKey()
if (!(await waitFor(pid, 'dictation: stopped', 8))) {
  finish(1, 'HOTKEY: FALHA - apertei ' + key + ' de novo e o ditado NAO parou')
}
console.log('   ' + key + ' -> ditado parou: OK')

// The take is silence, so empty text is the right answer -- what matters is the round trip closing.
if (!(await waitFor(pid, 'transcribed:', 30))) {
  finish(1, 'HOTKEY: FALHA - o audio nunca chegou ao motor')
}
console.log('   audio chegou ao motor e voltou: OK')

console.log('HOTKEY: PASSA - a tecla comeca e termina um ditado de verdade')
finish(0)
