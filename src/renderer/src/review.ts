// Review card; keys match the Flutter app: Enter sends, Tab and Esc discard.
import { applyI18n, t, type Lang } from '../../shared/i18n'
import type { ReviewPayload } from '../../shared/ipc'

const root = document.body
const text = document.getElementById('text') as HTMLTextAreaElement
const target = document.getElementById('target') as HTMLElement
const sendButton = document.getElementById('send') as HTMLButtonElement
const discardButton = document.getElementById('discard') as HTMLButtonElement

// One card resolves once: the key path and the button path can both fire for the same card.
let resolved = false

let lang: Lang = 'pt'
const ready = (async (): Promise<void> => {
  lang = await window.api.invoke('i18n:lang')
  applyI18n(document, lang)
  document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
})()

function finish(result: Parameters<typeof window.api.invoke<'review:resolve'>>[1]): void {
  if (resolved) return
  resolved = true
  root.dataset.closing = '1'
  // Let the exit animation play before the window goes away.
  setTimeout(() => void window.api.invoke('review:resolve', result), 140)
}

const send = (): void => finish({ action: 'send', text: text.value })
const discard = (): void => finish({ action: 'discard' })

function show(payload: ReviewPayload): void {
  resolved = false
  delete root.dataset.closing
  text.value = payload.text
  const kind = payload.targetKind === 'console' ? t(lang, 'reviewKindTerminal') : payload.targetKind
  target.textContent = payload.targetTitle ? payload.targetTitle + ' (' + kind + ')' : kind
  root.dataset.open = '1'
  text.focus()
  text.setSelectionRange(text.value.length, text.value.length)
}

window.api.on('review:show', (payload) => void ready.then(() => show(payload)))

// Belt and braces against ordering: if the payload was set before this screen existed, take it now.
void ready
  .then(() => window.api.invoke('review:pending'))
  .then((pending) => {
    if (pending && !text.value) show(pending)
  })

text.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
    return
  }
  if (e.key === 'Tab' || e.key === 'Escape') {
    e.preventDefault()
    discard()
  }
})

sendButton.addEventListener('click', send)
discardButton.addEventListener('click', discard)
