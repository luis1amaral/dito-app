// Proves the paste lands in every class of app the owner uses, not only in a raw console.
// One probe per CODE PATH: the console path lives in paste-wiring.mjs, the gui path is here.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const HERE = path.dirname(fileURLToPath(import.meta.url))
const native = require(path.join(HERE, '..', 'native', 'build', 'Release', 'dito_win32.node'))

const ELECTRON = path.join(HERE, '..', 'node_modules', 'electron', 'dist', 'electron.exe')
const CHROMIUM_TARGET = path.join(HERE, 'targets', 'chromium.js')
const TEXT = 'Ação e coração: hoje às 5, não é? Ótimo.'
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'dito-alvos-'))
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const ps = (cmd) => execFileSync('powershell', ['-NoProfile', '-Command', cmd], { encoding: 'utf8' })

// Windows refuses SetForegroundWindow to a process that does not own the foreground; tapping ALT
// releases that lock for the calling thread.
const FOCUS = `
Add-Type @'
using System; using System.Runtime.InteropServices;
public class F {
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindowW(string c, string t);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
  public static void Bring(string title) {
    IntPtr h = FindWindowW(null, title);
    if (h == IntPtr.Zero) return;
    keybd_event(0x12, 0, 0, IntPtr.Zero);
    keybd_event(0x12, 0, 2, IntPtr.Zero);
    ShowWindow(h, 9);
    uint owner = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero);
    AttachThreadInput(GetCurrentThreadId(), owner, true);
    SetForegroundWindow(h);
    AttachThreadInput(GetCurrentThreadId(), owner, false);
  }
}
'@
[F]::Bring('TITULO')
`

const failures = []
const kill = (pid) => {
  try {
    execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' })
  } catch {
    // Already gone is fine.
  }
}

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

async function probe(name, title, start, read) {
  console.log('-- ' + name)
  const out = path.join(TMP, name + '.txt')
  const pid = start(out)
  let target = null
  for (let i = 0; i < 20; i += 1) {
    ps(FOCUS.replace('TITULO', title))
    await wait(400)
    native.rememberTarget()
    target = native.currentTarget()
    if (target.title === title) break
  }
  if (!target || target.title !== title) {
    failures.push(name + ': nao consegui por em primeiro plano (achei "' + target?.title + '")')
    kill(pid)
    return
  }
  console.log('   alvo: classe="' + target.className + '" tipo=' + target.kind)

  const before = read(out)
  const ok = native.paste(TEXT)
  await wait(1400)
  const got = read(out)
  kill(pid)

  // Whatever the person types while the gate runs also lands here; what matters is that OUR text
  // arrived contiguous and with the accents intact.
  if (!got.includes(TEXT)) {
    failures.push(name + ': chegou "' + got.trim() + '"')
    console.log('   REPROVA: o texto nao chegou inteiro')
    return
  }
  const noise = got.length - before.length - TEXT.length
  console.log('   colar()=' + ok + ' · texto identico com acento: OK' + (noise > 0 ? ' (+' + noise + ' char digitados durante o teste)' : ''))
}

await waitForCleanSlate()

await probe(
  'chromium',
  'DITO_ALVO_CHROMIUM',
  (out) => Number(ps(`(Start-Process '${ELECTRON}' -ArgumentList '${CHROMIUM_TARGET}','${out}' -PassThru).Id`).trim()),
  (out) => {
    try {
      return fs.readFileSync(out, 'utf8')
    } catch {
      return ''
    }
  }
)

fs.rmSync(TMP, { recursive: true, force: true })

console.log('')
if (failures.length) {
  for (const f of failures) console.log('   ' + f)
  console.log('ALVOS: FALHA - ' + failures.length + ' classe(s) de aplicativo nao recebem o texto')
  process.exit(1)
}
console.log('ALVOS: PASSA - a via gui (WhatsApp, navegador, apps) recebe o texto inteiro')
process.exit(0)
