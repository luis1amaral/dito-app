// Settings; every option comes from the shared config types (docs/decisoes.md).
import { HOTKEYS, MODE_LABEL_KEYS, MODES, type Config } from '../../shared/config'
import { applyI18n, LANG_CHOICES, LANG_LABEL_KEYS, t, type Lang } from '../../shared/i18n'
import type { AppStatus, DownloadProgress } from '../../shared/ipc'
import type { ModelRow } from '../../shared/models'

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T
const all = <T extends HTMLElement>(sel: string): T[] => [...document.querySelectorAll<T>(sel)]

let config: Config
let lang: Lang = 'pt'
let progress: DownloadProgress | null = null

const escape = (raw: string): string => raw.replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' })[c] ?? c)
const mb = (b: number): string => (b / 1024 / 1024).toFixed(0) + ' MB'

// ------------------------------------------------------------------- navigation --
for (const button of all<HTMLButtonElement>('nav button')) {
  button.addEventListener('click', () => {
    for (const other of all<HTMLButtonElement>('nav button')) {
      other.setAttribute('aria-selected', String(other === button))
    }
    for (const pane of all<HTMLElement>('main > section')) {
      pane.toggleAttribute('data-active', pane.dataset.pane === button.dataset.pane)
    }
  })
}

// ----------------------------------------------------------------------- status --
function paintStatus(s: AppStatus): void {
  $('version').textContent = t(lang, 'versionPrefix') + s.version
  $('update-version').textContent = s.version
  $('update-status').textContent = s.update.text

  const box = $('model-error')
  box.hidden = !s.modelError
  if (s.modelError) {
    box.innerHTML = t(lang, 'modelErrorPrefix') + escape(s.modelError) +
      ' <button class="action" id="retry-model" style="margin-left:10px">' + t(lang, 'retryButton') + '</button>'
    $<HTMLButtonElement>('retry-model').addEventListener('click', async (e) => {
      const b = e.currentTarget as HTMLButtonElement
      b.disabled = true
      b.textContent = t(lang, 'downloadingEllipsis')
      await window.api.invoke('models:retry')
      void reloadModels()
    })
  }

  const cards = [
    { label: t(lang, 'engineLabel'), ok: s.engineReady, bad: false, text: s.engineReady ? t(lang, 'readyLabel') : t(lang, 'engineLoading') },
    {
      label: t(lang, 'hotkeyLabel'),
      ok: s.hook.installed,
      bad: !s.hook.installed,
      text: s.hook.installed ? config.key + t(lang, 'hotkeyActiveSuffix') : t(lang, 'hotkeyErrorPrefix') + s.hook.error + ')'
    },
    {
      label: t(lang, 'modelStatusLabel'),
      ok: !!s.modelId && !s.modelError,
      bad: !s.modelId,
      text: s.downloading
        ? t(lang, 'downloadingPercentPrefix') + Math.round((100 * s.downloading.done) / (s.downloading.total || 1)) + '%'
        : s.modelLabel ?? t(lang, 'noModelInstalled')
    }
  ]
  $('status').innerHTML = cards
    .map((c) => {
      const cls = c.ok ? 'ok' : c.bad ? 'bad' : 'warn'
      return '<div class="status ' + cls + '"><div class="label">' + c.label +
        '</div><div class="value"><span class="dot"></span>' + c.text + '</div></div>'
    })
    .join('')

  const good = s.engineReady && s.hook.installed && !!s.modelId
  $('footer').className = 'footer ' + (good ? 'ok' : 'bad')
  $('footer-text').textContent = good ? t(lang, 'footerReady') : t(lang, 'footerNotReady')
}

// ----------------------------------------------------------------------- models --
function paintModels(rows: ModelRow[]): void {
  $('models').innerHTML = rows
    .map((m) => {
      const badges =
        (m.active ? '<span class="badge in-use">' + t(lang, 'inUseBadge') + '</span>' : '') +
        (m.isDefault ? '<span class="badge is-default">' + t(lang, 'defaultBadge') + '</span>' : '')
      const meta = m.description + ' · ' + mb(m.bytes) + (m.installed ? t(lang, 'installedSuffix') : '')
      const busy = progress?.id === m.id
      let buttons = ''
      if (busy) buttons = '<button class="action" disabled>' + t(lang, 'downloadingEllipsis') + '</button>'
      else if (!m.installed) buttons = '<button class="action primary" data-download="' + m.id + '">' + t(lang, 'downloadButton') + '</button>'
      else {
        if (!m.active) buttons += '<button class="action" data-use="' + m.id + '">' + t(lang, 'useButton') + '</button>'
        buttons += '<button class="action danger" data-delete="' + m.id + '"' +
          (m.canDelete ? '' : ' disabled title="' + t(lang, 'deleteDisabledTitle') + '"') + '>' + t(lang, 'deleteButton') + '</button>'
      }
      const bar = busy
        ? '<div class="bar"><i style="width:' + Math.round((100 * progress!.done) / (progress!.total || 1)) + '%"></i></div>'
        : ''
      return '<div class="model"><div class="info"><div class="title">' + m.label + badges +
        '</div><div class="meta">' + meta + '</div>' + bar +
        '</div><div class="buttons">' + buttons + '</div></div>'
    })
    .join('')

  for (const b of all<HTMLButtonElement>('[data-download]')) {
    b.addEventListener('click', async () => {
      b.disabled = true
      try {
        paintModels(await window.api.invoke('models:download', b.dataset.download!))
      } catch (err) {
        alert(t(lang, 'downloadFailedPrefix') + (err as Error).message)
      }
      void reloadModels()
    })
  }
  for (const b of all<HTMLButtonElement>('[data-use]')) {
    b.addEventListener('click', async () => paintModels(await window.api.invoke('models:use', b.dataset.use!)))
  }
  for (const b of all<HTMLButtonElement>('[data-delete]')) {
    b.addEventListener('click', async () => {
      if (!confirm(t(lang, 'confirmDeleteModel'))) return
      try {
        paintModels(await window.api.invoke('models:delete', b.dataset.delete!))
      } catch (err) {
        alert((err as Error).message)
      }
    })
  }
}

async function reloadModels(): Promise<void> {
  paintModels(await window.api.invoke('models:list'))
}

window.api.on('models:progress', (p) => {
  progress = p
  void reloadModels()
})

// ------------------------------------------------------------------------ audio --
async function listMicrophones(): Promise<void> {
  try {
    await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    // Without permission the list comes back unlabelled; the default device still works.
  }
  const select = $<HTMLSelectElement>('microphone')
  for (const d of await navigator.mediaDevices.enumerateDevices()) {
    if (d.kind !== 'audioinput' || d.deviceId === 'default' || d.deviceId === 'communications') continue
    const option = document.createElement('option')
    option.value = d.deviceId
    option.textContent = d.label || t(lang, 'micEntryPrefix') + d.deviceId.slice(0, 6)
    select.appendChild(option)
  }
  select.value = config.microphone ?? ''
}

// ----------------------------------------------------------------------- history --
async function loadHistory(): Promise<void> {
  const items = await window.api.invoke('history:read')
  $('history-count').textContent = items.length ? items.length + t(lang, 'historyCountSuffix') : ''
  $('history').innerHTML = items.length
    ? items
        .map((i) => '<div class="history-row"><p>' + escape(i.text) + '</p><div class="when">' +
          new Date(i.at).toLocaleString(lang === 'pt' ? 'pt-BR' : 'en-US') + '</div></div>')
        .join('')
    : '<span class="empty">' + t(lang, 'historyEmpty') + '</span>'
}

// ------------------------------------------------------------------ static text --
function paintStaticText(): void {
  applyI18n(document, lang)
  document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'

  $('key').innerHTML = HOTKEYS.map((k) => '<option value="' + k + '">' + k + '</option>').join('')
  $('mode').innerHTML = MODES.map((m) => '<option value="' + m + '">' + t(lang, MODE_LABEL_KEYS[m]) + '</option>').join('')
  $('lang').innerHTML = LANG_CHOICES.map((l) => '<option value="' + l + '">' + t(lang, LANG_LABEL_KEYS[l]) + '</option>').join('')
  $<HTMLSelectElement>('key').value = config.key
  $<HTMLSelectElement>('mode').value = config.mode
  $<HTMLSelectElement>('lang').value = config.lang
  $<HTMLInputElement>('autoPaste').checked = config.autoPaste
  $<HTMLInputElement>('pressEnter').checked = config.pressEnter
  $<HTMLInputElement>('restoreClipboard').checked = config.restoreClipboard
  for (const k of all<HTMLElement>('kbd.t')) k.textContent = config.key
}

// ------------------------------------------------------------------------ saving --
async function save(): Promise<void> {
  config = await window.api.invoke('config:write', {
    key: $<HTMLSelectElement>('key').value as Config['key'],
    mode: $<HTMLSelectElement>('mode').value as Config['mode'],
    microphone: $<HTMLSelectElement>('microphone').value || null,
    autoPaste: $<HTMLInputElement>('autoPaste').checked,
    pressEnter: $<HTMLInputElement>('pressEnter').checked,
    restoreClipboard: $<HTMLInputElement>('restoreClipboard').checked,
    lang: $<HTMLSelectElement>('lang').value as Config['lang']
  })
  lang = await window.api.invoke('i18n:lang')
  paintStaticText()
  paintStatus(await window.api.invoke('status:read'))
  void reloadModels()
  void loadHistory()
}

// ------------------------------------------------------------------------ start --
async function main(): Promise<void> {
  config = await window.api.invoke('config:read')
  lang = await window.api.invoke('i18n:lang')
  paintStaticText()

  // Paint before awaiting the microphone: the permission prompt would block the screen.
  paintStatus(await window.api.invoke('status:read'))
  void reloadModels()
  void loadHistory()

  await listMicrophones()
  for (const id of ['key', 'mode', 'lang', 'microphone', 'autoPaste', 'pressEnter', 'restoreClipboard']) {
    $(id).addEventListener('change', () => void save())
  }
  $('clear-history').addEventListener('click', async () => {
    if (!confirm(t(lang, 'confirmClearHistory'))) return
    await window.api.invoke('history:clear')
    void loadHistory()
  })
  $('check-update').addEventListener('click', async (e) => {
    const b = e.currentTarget as HTMLButtonElement
    b.disabled = true
    b.textContent = t(lang, 'checkingEllipsis')
    const r = await window.api.invoke('update:check')
    $('update-status').textContent = r.text
    b.disabled = false
    b.textContent = t(lang, 'checkUpdateButton')
  })

  setInterval(async () => paintStatus(await window.api.invoke('status:read')), 1500)
  setInterval(() => void loadHistory(), 5000)
}

void main()
