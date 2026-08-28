// Gate: the update feed exists, answers, and serves the binary it announces -- per platform.
// Exists because 2.0.1 and 2.0.2 shipped with a broken feed and nobody noticed until the screen.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { humanError } from '../src/main/updater'

const ROOT = join(import.meta.dirname, '..')
const TIMEOUT_MS = 15000

let failures = 0

function ok(msg) {
  console.log('  ok   ' + msg)
}

function fail(msg) {
  console.log('  FALHA ' + msg)
  failures += 1
}

// With no network the gate is INCOMPLETE, never green: verify.mjs reads 2 as pending.
function incomplete(msg) {
  console.log('  PENDENTE ' + msg)
  process.exit(2)
}

async function get(url, extra = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    return await fetch(url, { signal: ctrl.signal, redirect: 'manual', ...extra })
  } catch (e) {
    incomplete(`sem resposta de ${url} (${e.message})`)
  } finally {
    clearTimeout(timer)
  }
}

const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'))
// The app reads the feed of the platform it runs on, so the gate has to check that same one.
const platform = process.platform === 'linux' ? 'linux' : 'win'
const channelFile = platform === 'linux' ? 'latest-linux.yml' : 'latest.yml'
const publish = pkg.build?.[platform]?.publish?.[0] ?? pkg.build?.publish?.[0]

if (publish?.provider !== 'generic') {
  fail(`build.${platform}.publish[0].provider e "${publish?.provider}", esperado "generic"`)
  process.exit(1)
}
if (!(publish.url ?? '').startsWith('https://')) {
  fail(`build.${platform}.publish[0].url invalida: ${publish?.url}`)
  process.exit(1)
}
ok(`feed de ${platform} configurado: ${publish.url}`)

const base = publish.url.replace(/\/+$/, '')

const channel = await get(`${base}/${channelFile}`)
if (channel.status !== 200) {
  fail(`GET ${base}/${channelFile} devolveu ${channel.status} — a release esta sem o ${channelFile} anexado`)
  process.exit(1)
}

const yaml = await channel.text()
const version = /^version:\s*(.+)$/m.exec(yaml)?.[1]?.trim()
if (!/^\d+\.\d+\.\d+/.test(version ?? '')) {
  fail(`${channelFile} sem version valida (${JSON.stringify(version)})`)
  process.exit(1)
}
ok(`${channelFile} anuncia a ${version}`)

const file = /^path:\s*(.+)$/m.exec(yaml)?.[1]?.trim()
if (!file) {
  fail(`${channelFile} sem campo path`)
  process.exit(1)
}

// One-byte range: proves the binary is reachable without pulling the whole 109 MB.
const bin = await get(`${base}/${file}`, { headers: { Range: 'bytes=0-0' } })
if (![200, 206, 301, 302, 307].includes(bin.status)) {
  fail(`GET ${base}/${file} devolveu ${bin.status}`)
  process.exit(1)
}
ok(`${file} alcancavel (${bin.status})`)

// A name that does not exist must 404: a feed answering 200 to everything would fool the updater.
const ghost = await get(`${base}/nao-existe-${Date.now()}.exe`)
if (ghost.status !== 404) fail(`asset inexistente devolveu ${ghost.status}, esperado 404`)
else ok('asset inexistente devolve 404')

// The defect behind this: 2.0.2 showed the whole HTTP dump in the Situacao field.
const RAW = '404 "method: GET url: https://github.com/luis1amaral/dito-app/releases.atom\n\n'
  + 'Please double check that your authentication token is correct." Headers: { "cache-control": '
  + '"no-cache", "content-encoding": "gzip", "set-cookie": [ "_gh_sess=4%2FBZgVdxPvSQCEHP2O" ] }'

const cases: Array<[string, string]> = [
  [RAW, 'código 404'],
  ['Cannot find channel "latest.yml" update info: HttpError: 404', 'manifesto'],
  ['getaddrinfo ENOTFOUND dito-api.defaltm.com', 'falar com o servidor'],
  ['algo que ninguem previu', 'log'],
]

for (const [input, expected] of cases) {
  const output = humanError(new Error(input))
  const label = input.slice(0, 34).replace(/\s+/g, ' ')
  if (!output.includes(expected)) fail(`humanError("${label}...") deu "${output}", esperava conter "${expected}"`)
  // No shred of the protocol may reach the screen, whatever the error was.
  else if (/method:|Headers:|url: http|set-cookie|_gh_sess/i.test(output)) fail(`humanError vazou protocolo: "${output}"`)
  else ok(`erro vira frase: "${output}"`)
}

process.exit(failures ? 1 : 0)
