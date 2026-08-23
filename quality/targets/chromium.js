// A minimal Chromium window with a text box: the class WhatsApp Desktop and any browser belong to.
const { app, BrowserWindow, ipcMain } = require('electron')
const { writeFileSync } = require('node:fs')

const out = process.argv[process.argv.length - 1]

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 520,
    height: 220,
    title: 'DITO_ALVO_CHROMIUM',
    webPreferences: { nodeIntegration: true, contextIsolation: false }
  })
  win.loadURL(
    'data:text/html;charset=utf-8,' +
      encodeURIComponent(`
        <body style="margin:0;background:#111;color:#eee;font:14px sans-serif">
          <textarea id="t" autofocus style="width:100%;height:180px;background:#000;color:#eee;border:0;padding:10px"></textarea>
          <script>
            const { ipcRenderer } = require('electron')
            const t = document.getElementById('t')
            t.focus()
            t.addEventListener('input', () => ipcRenderer.send('typed', t.value))
          </script>
        </body>`)
  )
  ipcMain.on('typed', (_e, value) => writeFileSync(out, value, 'utf8'))
  win.on('closed', () => app.quit())
})
