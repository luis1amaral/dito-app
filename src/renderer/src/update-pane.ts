// The Updates pane: one button that checks, shows how much came down, then installs and restarts.
import { t, type Lang, type MessageKey } from '../../shared/i18n'
import type { AppStatus } from '../../shared/ipc'

type UpdateState = AppStatus['update']

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T

const LABELS: Partial<Record<UpdateState['state'], MessageKey>> = {
  ready: 'restartAndUpdateButton',
  installing: 'updateInstalling',
  downloading: 'downloadingEllipsis'
}

export function paintUpdate(u: UpdateState, lang: Lang): void {
  const button = $<HTMLButtonElement>('check-update')
  $('update-bar').hidden = u.state !== 'downloading'
  if (u.state === 'downloading') $('update-fill').style.width = u.percent + '%'
  button.disabled = u.state === 'downloading' || u.state === 'checking' || u.state === 'installing'
  button.dataset.ready = u.state === 'ready' ? '1' : '0'
  button.textContent = t(lang, LABELS[u.state] ?? 'checkUpdateButton')
}

// Ready means the bytes are already on disk, so the same button installs instead of checking again.
export function bindUpdate(lang: () => Lang): void {
  $('check-update').addEventListener('click', async (e) => {
    const button = e.currentTarget as HTMLButtonElement
    const pronto = button.dataset.ready === '1'
    button.disabled = true
    if (!pronto) button.textContent = t(lang(), 'checkingEllipsis')
    const r = await window.api.invoke(pronto ? 'update:install' : 'update:check')
    $('update-status').textContent = r.text
    paintUpdate(r, lang())
  })
}
