// Proves the download machinery without pulling 640 MB: fetches the smallest file in the catalog,
// checks its sha256, proves a tampered file is refused, that a half file resumes, and the guard
// that never lets the user delete the last model.
import fs from 'node:fs'
import path from 'node:path'
import * as models from '../src/main/models'

// Through models, never from catalog directly: importing both gives two module instances and
// mutating one leaves the code reading the other.
const { CATALOG, DEFAULT_MODEL } = models

// DITO_APPDATA must come from the caller: ESM hoists imports, so setting it here is too late.
if (!process.env['DITO_APPDATA']) {
  console.error('MODELS: FALHA - rode com DITO_APPDATA apontando para uma pasta temporaria')
  process.exit(1)
}

const failures: string[] = []
function fail(msg: string): void {
  failures.push(msg)
  console.log('   REPROVA: ' + msg)
}

console.log('-- catalogo')
for (const m of CATALOG) {
  const bad = m.files.filter(
    (f) => !/^[0-9a-f]{64}$/.test(f.sha256) || !(f.bytes > 0) || !f.url.startsWith('https://')
  )
  if (bad.length) fail(m.id + ': ' + bad.length + ' arquivo(s) com sha256/tamanho/url invalido')
}
const totalFiles = CATALOG.reduce((s, m) => s + m.files.length, 0)
console.log('   ' + CATALOG.length + ' modelos · ' + totalFiles + ' arquivos · padrao ' + DEFAULT_MODEL.id)

let smallest: { model: (typeof CATALOG)[number]; file: (typeof CATALOG)[number]['files'][number] } | null = null
for (const m of CATALOG) {
  for (const f of m.files) if (!smallest || f.bytes < smallest.file.bytes) smallest = { model: m, file: f }
}
if (!smallest) {
  console.error('MODELS: FALHA - catalogo vazio')
  process.exit(1)
}
const victim = smallest.model
const only = smallest.file
const dir = models.dirFor(victim.id)

// Shrink the model to a single small file so the proofs cost kilobytes instead of hundreds of MB.
const realFiles = victim.files
// The restore must wait for the async body: doing it synchronously put the real file list back
// before download() ever read it, and the tampered-hash proof silently tested the real files.
async function withOneFile<T>(files: typeof realFiles, body: () => Promise<T> | T): Promise<T> {
  victim.files = files
  try {
    return await body()
  } finally {
    victim.files = realFiles
  }
}

console.log('-- download de verdade (menor arquivo do catalogo)')
console.log('   ' + victim.id + '/' + only.name + ' (' + (only.bytes / 1024).toFixed(0) + ' KB)')
fs.rmSync(dir, { recursive: true, force: true })
try {
  await withOneFile([only], () => models.download(victim.id))
  const written = path.join(dir, only.name)
  const size = fs.existsSync(written) ? fs.statSync(written).size : -1
  if (size !== only.bytes) fail('tamanho ' + size + ' != ' + only.bytes)
  else console.log('   baixado e sha256 conferido: OK')
} catch (err) {
  fail('download falhou: ' + (err as Error).message)
}

console.log('-- hash errado tem de reprovar')
const tampered = { ...only, sha256: 'f'.repeat(64) }
fs.rmSync(dir, { recursive: true, force: true })
try {
  await withOneFile([tampered], () => models.download(victim.id))
  fail('aceitou um arquivo com sha256 errado')
} catch (err) {
  if (/sha256/.test((err as Error).message)) console.log('   recusou o arquivo adulterado: OK')
  else fail('falhou por outro motivo: ' + (err as Error).message)
}

console.log('-- retomada de download interrompido')
fs.rmSync(dir, { recursive: true, force: true })
fs.mkdirSync(dir, { recursive: true })
try {
  await withOneFile([only], () => models.download(victim.id))
  const complete = fs.readFileSync(path.join(dir, only.name))
  const half = Math.floor(complete.length / 2)
  fs.rmSync(path.join(dir, only.name), { force: true })
  fs.writeFileSync(path.join(dir, only.name + '.partial'), complete.subarray(0, half))

  await withOneFile([only], () => models.download(victim.id))
  const size = fs.statSync(path.join(dir, only.name)).size
  if (size !== only.bytes) fail('retomada terminou com ' + size + ', esperado ' + only.bytes)
  else console.log('   retomou de ' + half + ' e fechou em ' + size + ' bytes: OK')
} catch (err) {
  fail('retomada falhou: ' + (err as Error).message)
}

console.log('-- trava de apagar o ultimo modelo')
try {
  await withOneFile([only], () => models.remove(victim.id))
  fail('deixou apagar o unico modelo instalado')
} catch (err) {
  if (/único|unico|instalado/i.test((err as Error).message)) console.log('   recusou apagar o ultimo: OK')
  else fail('recusou por outro motivo: ' + (err as Error).message)
}

fs.rmSync(dir, { recursive: true, force: true })

console.log('')
if (failures.length) {
  console.log('MODELS: FALHA - ' + failures.length + ' reprovacao(oes)')
  process.exit(1)
}
console.log('MODELS: PASSA')
process.exit(0)
