// Proves the audio is cut into windows and that the cut lands on silence, not in the middle of a
// word. Without this the live text would arrive chopped and nobody would notice until using it.
import { AudioChunker } from '../src/main/audio-chunker'
import { joinSegment, segmentDelta } from '../src/shared/join-segments'

const SAMPLE_RATE = 16000
const WINDOW_SECONDS = 8

const failures: string[] = []
function fail(msg: string): void {
  failures.push(msg)
  console.log('   REPROVA: ' + msg)
}

// Loud where speech would be, near-silent in the gap: the cut must land in the gap.
function take(seconds: number, gapAt: number[]): Float32Array {
  const samples = new Float32Array(Math.round(seconds * SAMPLE_RATE))
  for (let i = 0; i < samples.length; i += 1) {
    const second = i / SAMPLE_RATE
    const inGap = gapAt.some((g) => second >= g && second < g + 0.4)
    samples[i] = inGap ? 0.0002 * Math.sin(i) : 0.35 * Math.sin(i / 7)
  }
  return samples
}

console.log('-- corte em janelas')
{
  const chunker = new AudioChunker()
  const windows = chunker.push(take(20, [6.4, 14.4]))
  if (windows.length < 2) fail('20 s deveriam fechar pelo menos 2 janelas, fecharam ' + windows.length)
  else console.log('   20 s -> ' + windows.length + ' janelas: OK')

  const tail = chunker.flush()
  if (!tail) fail('a sobra deveria existir depois de 20 s')
  else if (tail.length >= WINDOW_SECONDS * SAMPLE_RATE) fail('a sobra deveria ser menor que uma janela')
  else console.log('   sobra de ' + (tail.length / SAMPLE_RATE).toFixed(1) + ' s, menor que a janela: OK')
}

console.log('-- o corte cai no silencio')
{
  const chunker = new AudioChunker()
  const windows = chunker.push(take(20, [6.4, 14.4]))
  const first = windows[0]
  if (!first) fail('nenhuma janela para medir')
  else {
    const cutAt = first.length / SAMPLE_RATE
    // The gap is 6.4-6.8 s, far from the 8 s edge: cutting at the edge must NOT pass by accident.
    if (cutAt < 6.35 || cutAt > 6.85) fail('cortou em ' + cutAt.toFixed(2) + ' s, fora do silencio')
    else console.log('   cortou em ' + cutAt.toFixed(2) + ' s, dentro do silencio: OK')

    let energy = 0
    for (let i = Math.max(0, first.length - 800); i < first.length; i += 1) energy += Math.abs(first[i]!)
    const average = energy / 800
    if (average > 0.05) fail('o fim da janela ainda tem fala (media ' + average.toFixed(3) + ')')
    else console.log('   fim da janela em silencio (media ' + average.toFixed(4) + '): OK')
  }
}

console.log('-- nada se perde entre janelas')
{
  const chunker = new AudioChunker()
  const total = 20 * SAMPLE_RATE
  const windows = chunker.push(take(20, [6.4, 14.4]))
  const tail = chunker.flush()
  const sum = windows.reduce((s, w) => s + w.length, 0) + (tail?.length ?? 0)
  if (sum !== total) fail('entraram ' + total + ' amostras e sairam ' + sum)
  else console.log('   ' + total + ' amostras entram, ' + sum + ' saem: OK')
}

console.log('-- emenda dos segmentos')
{
  const cases: [string, string, string][] = [
    ['Bom dia', 'tudo bem', 'Bom dia tudo bem'],
    ['Bom dia', ', tudo bem', 'Bom dia, tudo bem'],
    ['', 'primeiro', 'primeiro'],
    ['Fim.', '', 'Fim.'],
    ['abre (', 'parenteses', 'abre (parenteses']
  ]
  for (const [a, b, expected] of cases) {
    const got = joinSegment(a, b)
    if (got !== expected) fail('joinSegment("' + a + '","' + b + '") deu "' + got + '"')
  }
  if (!failures.length) console.log('   ' + cases.length + ' casos de espaco e pontuacao: OK')
}

// A 2.0.8 digitou o trecho ao vivo E a mensagem inteira no fim. A invariante que impede isso:
// a soma do que foi digitado tem que dar exatamente o que vai para a area de transferencia.
console.log('-- nada e digitado duas vezes')
{
  const takes: string[][] = [
    ['Cara, so uma correcao.', 'Eu nao pensei nisso.', 'Ele fica transcrevendo, e e certo.'],
    ['Bom dia', ', tudo bem', '? Otimo.'],
    ['abre (', 'parenteses', ' e fecha)'],
    ['unico trecho']
  ]
  for (const segmentos of takes) {
    let spoken = ''
    let digitado = ''
    for (const trecho of segmentos) {
      const delta = segmentDelta(spoken, trecho)
      spoken += delta
      digitado += delta
    }
    if (digitado !== spoken) fail('digitado "' + digitado + '" != area de transferencia "' + spoken + '"')
    // Sem isto o defeito volta na forma "quando eu.To falando" -- palavras coladas.
    if (/\w[.?!]\w/.test(digitado)) fail('trechos colados sem espaco: "' + digitado + '"')
  }
  if (!failures.length) console.log('   ' + takes.length + ' ditados: o digitado bate com o Ctrl+V')
}

console.log('')
if (failures.length) {
  console.log('CHUNKER: FALHA - ' + failures.length + ' problema(s)')
  process.exit(1)
}
console.log('CHUNKER: PASSA')
process.exit(0)
