// Proves the "Sem som" warning fires when nothing arrives and NEVER when the speaker just pauses.
//
// Measured on this machine on 2026-08-25, 93 blocks of 4096 frames at 48 kHz each time:
//   microphone working, quiet room -> zero null blocks, rms from 6.3e-6 to 5.8e-3
//   same microphone muted          -> all 93 blocks null, rms exactly 0
// The old rule (rms < 0.006 for 2 s) called BOTH of those "sem som" and fired in 56 of the 159
// takes in the real log. The floor fixture below is that measurement, so a threshold rule cannot
// pass this gate again.
import { DEAD_INPUT_MS, MicSignalWatch, WARMUP_MS } from '../src/shared/mic-signal'

const BLOCK_MS = 4096 / 48 // one ScriptProcessor block at 48 kHz
// One block arms the counter and another crosses the deadline, so the warning lands two blocks late.
const SLACK_MS = 2 * BLOCK_MS
const OLD_THRESHOLD = 0.006

const failures: string[] = []
function fail(msg: string): void {
  failures.push(msg)
  console.log('   REPROVA: ' + msg)
}

/** Measured noise floor of a working microphone in a quiet room; never null, always below 0.006. */
function floorRms(i: number): number {
  const scale = [6.3e-6, 1.5e-5, 8.3e-5, 4.1e-4, 1.85e-3, 5.769e-3]
  return scale[i % scale.length]!
}

/** Runs a take and answers when the warning first fired, or null if it never did. */
function firstWarning(rmsAt: (block: number) => number, seconds: number): number | null {
  const watch = new MicSignalWatch()
  const start = 1_000_000
  watch.start(start)
  const blocks = Math.round((seconds * 1000) / BLOCK_MS)
  for (let i = 0; i < blocks; i += 1) {
    const now = start + Math.round(i * BLOCK_MS)
    if (watch.isDead(rmsAt(i), now)) return now - start
  }
  return null
}

console.log('-- microfone bom: pausa nunca vira falha')
{
  const at = firstWarning(floorRms, 300)
  if (at !== null) fail('acusou "sem som" aos ' + at + ' ms em 5 min de sala silenciosa')
  else console.log('   5 min no piso de ruido medido, nenhum aviso: OK')

  // The exact shape of the real complaint: press the key, think, speak, pause, speak again.
  const fala = (i: number): number => (i * BLOCK_MS > 8000 && i * BLOCK_MS < 40_000 ? 0.12 : floorRms(i))
  const pausado = firstWarning(fala, 120)
  if (pausado !== null) fail('acusou "sem som" aos ' + pausado + ' ms num ditado com pausas')
  else console.log('   8 s pensando + fala + 80 s de pausa, nenhum aviso: OK')
}

console.log('-- microfone mudo: acusa, e acusa rapido')
{
  const at = firstWarning(() => 0, 30)
  if (at === null) fail('microfone mudo passou 30 s sem nenhum aviso')
  else if (at < WARMUP_MS) fail('avisou aos ' + at + ' ms, antes do aquecimento de ' + WARMUP_MS + ' ms')
  else if (at > WARMUP_MS + DEAD_INPUT_MS + SLACK_MS) fail('demorou ' + at + ' ms para avisar')
  else console.log('   avisou aos ' + at + ' ms (aquecimento ' + WARMUP_MS + ' + ' + DEAD_INPUT_MS + '): OK')

  // Someone hits the hardware mute button halfway through: that must still be caught.
  const morreNoMeio = (i: number): number => (i * BLOCK_MS < 10_000 ? 0.1 : 0)
  const meio = firstWarning(morreNoMeio, 30)
  if (meio === null) fail('microfone que emudece no meio do ditado nao foi acusado')
  else if (meio > 10_000 + DEAD_INPUT_MS + SLACK_MS) fail('demorou ' + meio + ' ms para acusar o mudo do meio')
  else console.log('   emudeceu aos 10 s, acusado aos ' + meio + ' ms: OK')
}

console.log('-- o aviso some quando o som volta')
{
  const watch = new MicSignalWatch()
  watch.start(0)
  let avisou = false
  for (let ms = 0; ms <= 6000; ms += BLOCK_MS) if (watch.isDead(0, ms)) avisou = true
  if (!avisou) fail('nao avisou nos 6 s de silencio digital')
  else if (watch.isDead(0.05, 6100)) fail('continuou acusando "sem som" depois de o som voltar')
  else console.log('   avisou no vazio e parou de avisar quando o som voltou: OK')
}

// The gate has to reject the rule it replaced, or it is not a gate: run the OLD rule against the
// SAME measured floor and require it to fire. If it ever stops firing, this fixture went fake.
console.log('-- contraprova: a regra antiga reprovaria a fixture')
{
  let quietSince = 0
  let antigaAvisou = false
  const blocks = Math.round(60_000 / BLOCK_MS)
  for (let i = 0; i < blocks; i += 1) {
    const now = Math.round(i * BLOCK_MS)
    if (now < WARMUP_MS) continue
    if (floorRms(i) >= OLD_THRESHOLD) {
      quietSince = 0
      continue
    }
    if (!quietSince) quietSince = now
    if (now - quietSince >= DEAD_INPUT_MS) antigaAvisou = true
  }
  if (!antigaAvisou) fail('a fixture nao reproduz o defeito: a regra antiga tambem passaria nela')
  else console.log('   limiar de ' + OLD_THRESHOLD + ' acusa a sala silenciosa; a regra nova nao: OK')
}

console.log('')
if (failures.length) {
  console.log('SINAL DO MICROFONE: FALHA - ' + failures.length + ' problema(s)')
  process.exit(1)
}
console.log('SINAL DO MICROFONE: PASSA')
process.exit(0)
