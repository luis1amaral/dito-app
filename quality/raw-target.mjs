// Alvo de console em MODO CRU: setRawMode desliga PROCESSED_INPUT, que e o estado em que o
// Claude Code e o Gemini CLI poem o console -- e onde Ctrl+V chega como 0x16 em vez de colar.
// Peca que faltava em dito-app/tool/sonda_paste.ps1 (referenciava sonda_alvo_cru.js, inexistente).
import fs from 'node:fs'

const saida = process.argv[2]
if (!saida) {
  console.error('uso: node raw-target.mjs <arquivo-de-saida>')
  process.exit(1)
}
fs.writeFileSync(saida, '')

process.stdin.setRawMode(true)
process.stdin.resume()
process.stdin.setEncoding('utf8')

console.log('ALVO CRU pronto — modo cru ligado, escrevendo o que chegar em:')
console.log(saida)
console.log('(Ctrl+C nao sai: feche a janela)')

process.stdin.on('data', (pedaco) => {
  fs.appendFileSync(saida, pedaco)
  // eslint-disable-next-line no-control-regex -- showing control bytes IS the point here
  const visivel = pedaco.replace(/[\x00-\x1f]/g, (c) => '<' + c.charCodeAt(0).toString(16).padStart(2, '0') + '>')
  process.stdout.write(visivel)
})
