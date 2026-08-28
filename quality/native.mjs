// Proves the addon loads and that the hook REALLY installs. install_error != 0 = blind hook.
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
const require = createRequire(import.meta.url)
const HERE = path.dirname(fileURLToPath(import.meta.url))

const ADDON = process.platform === 'linux' ? 'dito_linux.node' : 'dito_win32.node'
// F9 and not the app's default: XGrabKey is exclusive, so the installed app would lose the grab.
const KEY = 'F9'

let native
try {
  native = require(path.join(HERE, '..', 'native', 'build', 'Release', ADDON))
} catch (err) {
  console.error('NATIVE: FALHA - addon nao carregou:', err.message)
  process.exit(1)
}
console.log('NATIVE: addon carregou ·', ADDON, '·', Object.keys(native).join(' '))

const ok = native.startHook(KEY, (e) => console.log('   evento:', JSON.stringify(e)))
const st = native.hookStatus()
console.log(`NATIVE: startHook=${ok} · installed=${st.installed} · error=${st.error}`)

const target = native.currentTarget()
console.log(`NATIVE: target · className="${target.className}" kind=${target.kind}`)

setTimeout(() => {
  const st2 = native.hookStatus()
  console.log(`NATIVE: apos 2s · installed=${st2.installed} · keys seen=${st2.seen} · pumps=${st2.pumps}`)
  native.stopHook()
  if (!st.installed) {
    console.error('NATIVE: FALHA - hook nao instalou (erro ' + st.error + ')')
    process.exit(1)
  }
  if (st2.pumps === 0) {
    console.error('NATIVE: FALHA - laco de eventos parado; o hook ficaria cego em silencio')
    process.exit(1)
  }
  console.log('NATIVE: PASSA')
  process.exit(0)
}, 2000)
