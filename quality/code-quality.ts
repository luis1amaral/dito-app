// Project rules no linter knows about. Each one exists because it already cost us something.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { extname, join, relative } from 'node:path'

const ROOT = join(import.meta.dirname, '..')
const MAX_FILE_LINES = 260
const MAX_COMMENT_LINES = 1

type Finding = { rule: string; where: string; detail: string }
const findings: Finding[] = []
const SKIP = new Set(['node_modules', 'build', 'out', 'dist'])

function fail(rule: string, where: string, detail: string): void {
  findings.push({ rule, where, detail })
}

function walk(dir: string, exts: string[]): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      if (SKIP.has(name)) continue
      out.push(...walk(full, exts))
    } else if (exts.includes(extname(name))) {
      out.push(full)
    }
  }
  return out
}

const rel = (f: string): string => relative(ROOT, f).replace(/\\/g, '/')

const sourceFiles = [...walk(join(ROOT, 'src'), ['.ts']), ...walk(join(ROOT, 'native', 'src'), ['.cc', '.cpp', '.h'])]
const screenFiles = walk(join(ROOT, 'src', 'renderer'), ['.html'])

// 1. A comment longer than one line means the why belongs in _docs/, with a pointer here.
for (const file of sourceFiles) {
  const lines = readFileSync(file, 'utf8').split('\n')
  let i = 0
  while (i < lines.length) {
    if (lines[i]!.trim().startsWith('//')) {
      let j = i
      while (j + 1 < lines.length && lines[j + 1]!.trim().startsWith('//')) j += 1
      const span = j - i + 1
      if (span > MAX_COMMENT_LINES) fail('comentario', rel(file) + ':' + (i + 1), span + ' linhas')
      i = j + 1
    } else {
      i += 1
    }
  }
}

// 2. A file doing many jobs is the shape index.js had when it broke; keep them small.
for (const file of sourceFiles) {
  const count = readFileSync(file, 'utf8').split('\n').length
  if (count > MAX_FILE_LINES && !rel(file).endsWith('catalog.ts')) {
    fail('arquivo grande', rel(file), count + ' linhas (teto ' + MAX_FILE_LINES + ')')
  }
}

// 3. A channel declared and never handled, or handled and never declared, is a dead wire.
const contract = readFileSync(join(ROOT, 'src', 'shared', 'ipc.ts'), 'utf8')
const mainSource = walk(join(ROOT, 'src', 'main'), ['.ts']).map((f) => readFileSync(f, 'utf8')).join('\n')
const rendererSource = [...walk(join(ROOT, 'src', 'renderer'), ['.ts']), ...walk(join(ROOT, 'src', 'preload'), ['.ts'])]
  .map((f) => readFileSync(f, 'utf8'))
  .join('\n')

function channelsIn(block: string): string[] {
  const start = contract.indexOf('export type ' + block + ' = {')
  if (start < 0) return []
  const end = contract.indexOf('\n}', start)
  return [...contract.slice(start, end).matchAll(/^ +'?([a-zA-Z:-]+)'?:/gm)].map((m) => m[1]!)
}

for (const channel of channelsIn('InvokeMap')) {
  if (!mainSource.includes("'" + channel + "'")) fail('canal orfao', channel, 'declarado mas nenhum handler no main')
  if (!rendererSource.includes("'" + channel + "'")) fail('canal orfao', channel, 'declarado mas nenhuma tela usa')
}
for (const channel of channelsIn('EventMap')) {
  if (!mainSource.includes("'" + channel + "'")) fail('canal orfao', channel, 'evento que ninguem envia')
  if (!rendererSource.includes("'" + channel + "'")) fail('canal orfao', channel, 'evento que ninguem escuta')
}

// 4. console bypasses the log file, the only trace after a crash. Only the gates may use it.
for (const file of walk(join(ROOT, 'src'), ['.ts'])) {
  const text = readFileSync(file, 'utf8')
  if (/\bconsole\.(log|error|warn|info|debug|trace)\(/.test(text) && !rel(file).endsWith('logger.ts')) {
    fail('console', rel(file), 'o produto nao usa console; no processo principal use log()')
  }
}

// 5. A string shared with the addon must come from the addon; a second copy drifts (2.0.0).
const addon = readFileSync(join(ROOT, 'native', 'src', 'addon.cc'), 'utf8')
const exported = new Set([...addon.matchAll(/exports\.Set\("([a-zA-Z]+)"/g)].map((m) => m[1]!))
const action = /kAction = "([a-z]+)"/.exec(addon)?.[1]
if (action && mainSource.includes("'" + action + "'")) {
  fail('literal duplicado', 'native ACTION', 'o main repete "' + action + '" em vez de usar native.action()')
}
for (const name of ['startHook', 'stopHook', 'paste']) {
  if (!exported.has(name)) fail('addon', name, 'export sumiu do addon')
}

// 6. Screen text belongs to i18n, not to the markup; this counts what is still hardcoded.
let hardcoded = 0
for (const file of screenFiles) {
  const text = readFileSync(file, 'utf8')
  hardcoded += [...text.matchAll(/>[^<>{}]*[áàâãéêíóôõúçÁÉÍÓÚÇ][^<>{}]*</g)].length
}

console.log('-- regras do projeto')
console.log('   arquivos analisados: ' + sourceFiles.length)
console.log('   texto de tela fixo no HTML: ' + hardcoded)
for (const f of findings) console.log('   REPROVA [' + f.rule + '] ' + f.where + ' — ' + f.detail)

console.log('')
if (findings.length) {
  console.log('QUALIDADE: FALHA - ' + findings.length + ' problema(s)')
  process.exit(1)
}
console.log('QUALIDADE: PASSA')
process.exit(0)
