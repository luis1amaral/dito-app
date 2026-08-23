// Portao 2: prova que o addon digita dentro de um console em MODO CRU e o texto chega inteiro.
// Reusa a receita de dito-app/tool/sonda_paste.ps1 (Start-Process cmd /k <bat>, espera o
// MainWindowHandle) e a peca de leitura que faltava, quality/raw-target.mjs.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
const require = createRequire(import.meta.url)
const AQUI = path.dirname(fileURLToPath(import.meta.url))
const native = require(path.join(AQUI, '..', 'native', 'build', 'Release', 'dito_win32.node'))

// Frase curta com acento pt-BR: prova que o metodo nao corrompe caractere.
const TEXTO = 'Ação e coração: hoje às 5, não é? Ótimo.'
const tmp = path.join(os.tmpdir(), 'dito_portao2')
fs.mkdirSync(tmp, { recursive: true })
const recebido = path.join(tmp, 'recebido.txt')
const bat = path.join(tmp, 'subir_alvo.bat')
const nodeExe = process.execPath
fs.writeFileSync(bat, `@echo off\r\nchcp 65001 >nul\r\ntitle DITO_ALVO_CRU\r\n"${nodeExe}" "${path.join(AQUI, 'raw-target.mjs')}" "${recebido}"\r\n`, 'ascii')
try { fs.unlinkSync(recebido) } catch {}

const espera = (ms) => new Promise((r) => setTimeout(r, ms))
const ps = (cmd) => execFileSync('powershell', ['-NoProfile', '-Command', cmd], { encoding: 'utf8' }).trim()

const pid = Number(ps(`(Start-Process cmd.exe -ArgumentList '/k','${bat}' -PassThru).Id`))
console.log(`alvo subiu: pid ${pid}`)

function encerrar(code) {
  try { execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
  process.exit(code)
}

// A janela do console demora a existir: a sonda espera ate 20 s pelo MainWindowHandle.
let h = 0
for (let i = 0; i < 40 && !h; i += 1) {
  await espera(500)
  h = Number(ps(`$p = Get-Process -Id ${pid} -ErrorAction SilentlyContinue; if ($p) { $p.Refresh(); [int64]$p.MainWindowHandle } else { 0 }`))
}
if (!h) {
  console.error('PORTAO2: FALHA - o console nunca ganhou janela')
  encerrar(1)
}
console.log(`janela do console: ${h}`)

const FOCAR = `
Add-Type @'
using System; using System.Runtime.InteropServices;
public class F {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
}
'@
$h = [IntPtr]${h}
[void][F]::ShowWindow($h, 9)
$dono = [F]::GetWindowThreadProcessId([F]::GetForegroundWindow(), [IntPtr]::Zero)
$meu = [F]::GetCurrentThreadId()
[void][F]::AttachThreadInput($meu, $dono, $true)
[void][F]::SetForegroundWindow($h)
[void][F]::AttachThreadInput($meu, $dono, $false)
`

let target = null
for (let i = 0; i < 10; i += 1) {
  ps(FOCAR)
  await espera(400)
  native.rememberTarget()
  target = native.currentTarget()
  if (target.className === 'ConsoleWindowClass') break
}
console.log(`alvo lembrado: classe="${target?.className}" titulo="${target?.title}" tipo=${target?.kind}`)

// Trava: nunca injetar se o primeiro plano nao for exatamente o alvo que esta sonda subiu.
if (target?.className !== 'ConsoleWindowClass') {
  console.error('PORTAO2: FALHA - o console nao ficou em primeiro plano; nao injeto em janela alheia')
  encerrar(1)
}
if (target.kind !== 'console') {
  console.error(`PORTAO2: FALHA - ClassificarAlvo devolveu "${target.kind}", esperado "console"`)
  encerrar(1)
}

const ok = native.paste(TEXTO)
await espera(1500)

let chegou = ''
try { chegou = fs.readFileSync(recebido, 'utf8') } catch {}

console.log(`colar() = ${ok}`)
console.log(`enviado: ${TEXTO}`)
console.log(`chegou:  ${chegou}`)
if (chegou !== TEXTO) {
  console.error('PORTAO2: FALHA - o texto que chegou ao console cru nao e igual ao enviado')
  encerrar(1)
}
console.log('PORTAO2: PASSA - texto inteiro, acento intacto, dentro de um console em modo cru')
encerrar(0)
