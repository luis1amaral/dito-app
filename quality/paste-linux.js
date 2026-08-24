// Linux paste gate: real Electron clipboard, real X11 target, real file on disk.
const { app, clipboard } = require('electron')
const { execFileSync, spawn } = require('node:child_process')
const { readFileSync, writeFileSync, existsSync } = require('node:fs')
const { join } = require('node:path')

const ADDON = join(__dirname, '..', 'native', 'build', 'Release', 'dito_linux.node')
const FILE = '/tmp/dito-gate-paste.txt'
const TEXT = 'teste com acentuação, ção e ênfase'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const xdo = (...args) => execFileSync('xdotool', args, { encoding: 'utf8' }).trim()

app.commandLine.appendSwitch('no-sandbox')

app.on('ready', async () => {
  let code = 1
  try {
    const addon = require(ADDON)
    writeFileSync(FILE, '')
    const editor = spawn('xed', [FILE], { detached: true, stdio: 'ignore' })
    await sleep(3000)

    const win = xdo('search', '--name', 'dito-gate-paste').split('\n')[0]
    xdo('windowactivate', '--sync', win)
    await sleep(600)

    addon.rememberTarget()
    const target = addon.currentTarget()
    console.log('ALVO:', JSON.stringify(target))
    console.log('ALVO EH O ATIVO:', addon.targetIsForeground())

    clipboard.writeText(TEXT)
    await sleep(250)
    const pasted = addon.paste(TEXT)
    console.log('paste() =', pasted)
    await sleep(800)

    const typed = addon.typeText(' | digitado: ação')
    console.log('typeText() =', typed)
    await sleep(1500)

    xdo('key', 'ctrl+s')
    await sleep(1500)

    const content = existsSync(FILE) ? readFileSync(FILE, 'utf8') : ''
    console.log('ARQUIVO:', JSON.stringify(content))
    const okPaste = content.includes(TEXT)
    const okType = content.includes('digitado: ação')
    console.log('RESULTADO: colagem=' + okPaste + ' digitacao=' + okType)
    code = okPaste && okType ? 0 : 1

    try { process.kill(-editor.pid) } catch { /* already gone */ }
  } catch (err) {
    console.log('FALHOU:', err.message)
  }
  app.exit(code)
})
