// Prova que o addon carrega e que o hook REALMENTE instala. install_error != 0 = hook cego.
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
const require = createRequire(import.meta.url)
const AQUI = path.dirname(fileURLToPath(import.meta.url))

let native
try {
  native = require(path.join(AQUI, '..', 'native', 'build', 'Release', 'dito_win32.node'))
} catch (err) {
  console.error('NATIVE: FALHA - addon nao carregou:', err.message)
  process.exit(1)
}
console.log('NATIVE: addon carregou ·', Object.keys(native).join(' '))

const ok = native.startHook('F9', (e) => console.log('   evento:', JSON.stringify(e)))
const st = native.hookStatus()
console.log(`NATIVE: startHook=${ok} · installed=${st.installed} · winError=${st.error}`)

const target = native.currentTarget()
console.log(`NATIVE: target · className="${target.className}" kind=${target.kind}`)

setTimeout(() => {
  const st2 = native.hookStatus()
  console.log(`NATIVE: apos 2s · installed=${st2.installed} · keys seen=${st2.seen} · pumps=${st2.pumps}`)
  native.stopHook()
  if (!st.installed) {
    console.error('NATIVE: FALHA - hook nao instalou (erro Win32 ' + st.error + ')')
    process.exit(1)
  }
  if (st2.pumps === 0) {
    console.error('NATIVE: FALHA - message pump parado; o hook seria desinstalado em silencio')
    process.exit(1)
  }
  console.log('NATIVE: PASSA')
  process.exit(0)
}, 2000)
