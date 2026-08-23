// Alvo descartavel da sonda de colagem: le stdin em modo CRU e registra o que chega, com tempo.
// Mesmo modo de entrada do Claude Code / Gemini CLI (Ink -> setRawMode): a sonda confere que o
// GetConsoleMode deste processo bate com o da sessao real antes de dar a tabela por valida.
const fs = require('fs');

const saida = process.argv[2];
if (!saida) {
  console.error('uso: node sonda_alvo_cru.js <arquivo-de-saida>');
  process.exit(2);
}
fs.writeFileSync(saida, '');

if (!process.stdin.isTTY) {
  console.error('ERRO: stdin nao e um TTY, o alvo precisa de um console de verdade');
  process.exit(3);
}

process.stdin.setRawMode(true);
process.stdin.resume();
// DECSET 2004: o Claude Code liga bracketed paste, entao o proxy tem de ligar tambem.
const ESC = String.fromCharCode(27);
process.stdout.write(ESC + '[?2004h');
process.on('exit', () => { try { process.stdout.write(ESC + '[?2004l'); } catch (_) {} });

const inicio = process.hrtime.bigint();
process.stdin.on('data', (b) => {
  const ms = Number((process.hrtime.bigint() - inicio) / 1000000n);
  fs.appendFileSync(
    saida,
    JSON.stringify({ ms, hex: b.toString('hex'), texto: b.toString('utf8') }) + '\n',
  );
  if (b.length === 1 && b[0] === 0x03) process.exit(0);
});

console.log('ALVO CRU PRONTO pid=' + process.pid);
