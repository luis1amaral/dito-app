// Portao: o feed de atualizacao existe, responde e serve o binario que anuncia.
// Existe porque a 2.0.1 e a 2.0.2 sairam com o feed quebrado e ninguem percebeu ate abrir a tela.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { humanError } from '../src/main/updater'

const RAIZ = join(import.meta.dirname, '..')
const TIMEOUT_MS = 15000

let falhas = 0

function ok(msg) {
  console.log('  ok   ' + msg)
}

function falhou(msg) {
  console.log('  FALHA ' + msg)
  falhas += 1
}

// Sem rede o portao e INCOMPLETO, nunca verde: verify.ps1 trata 2 como pendente.
function incompleto(msg) {
  console.log('  PENDENTE ' + msg)
  process.exit(2)
}

async function buscar(url, extra = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    return await fetch(url, { signal: ctrl.signal, redirect: 'manual', ...extra })
  } catch (e) {
    incompleto(`sem resposta de ${url} (${e.message})`)
  } finally {
    clearTimeout(timer)
  }
}

const pkg = JSON.parse(readFileSync(join(RAIZ, 'package.json'), 'utf8'))
const publish = pkg.build?.publish?.[0]

if (publish?.provider !== 'generic') {
  falhou(`build.publish[0].provider e "${publish?.provider}", esperado "generic"`)
  process.exit(1)
}
if (!(publish.url ?? '').startsWith('https://')) {
  falhou(`build.publish[0].url invalida: ${publish?.url}`)
  process.exit(1)
}
ok(`feed configurado: ${publish.url}`)

const base = publish.url.replace(/\/+$/, '')

const canal = await buscar(`${base}/latest.yml`)
if (canal.status !== 200) {
  falhou(`GET ${base}/latest.yml devolveu ${canal.status} — a release esta sem o latest.yml anexado`)
  process.exit(1)
}

const yaml = await canal.text()
const versao = /^version:\s*(.+)$/m.exec(yaml)?.[1]?.trim()
if (!/^\d+\.\d+\.\d+/.test(versao ?? '')) {
  falhou(`latest.yml sem version valida (${JSON.stringify(versao)})`)
  process.exit(1)
}
ok(`latest.yml anuncia a ${versao}`)

const arquivo = /^path:\s*(.+)$/m.exec(yaml)?.[1]?.trim()
if (!arquivo) {
  falhou('latest.yml sem campo path')
  process.exit(1)
}

// Range de 1 byte: prova que o binario e alcancavel sem baixar os 109 MB.
const bin = await buscar(`${base}/${arquivo}`, { headers: { Range: 'bytes=0-0' } })
if (![200, 206, 301, 302, 307].includes(bin.status)) {
  falhou(`GET ${base}/${arquivo} devolveu ${bin.status}`)
  process.exit(1)
}
ok(`${arquivo} alcancavel (${bin.status})`)

// Um nome inexistente precisa dar 404: um feed que responde 200 pra tudo enganaria o updater.
const fantasma = await buscar(`${base}/nao-existe-${Date.now()}.exe`)
if (fantasma.status !== 404) falhou(`asset inexistente devolveu ${fantasma.status}, esperado 404`)
else ok('asset inexistente devolve 404')

// O defeito que motivou isto: a 2.0.2 mostrava o dump de HTTP inteiro no campo Situacao.
const CRU = '404 "method: GET url: https://github.com/luis1amaral/dito-app/releases.atom\n\n'
  + 'Please double check that your authentication token is correct." Headers: { "cache-control": '
  + '"no-cache", "content-encoding": "gzip", "set-cookie": [ "_gh_sess=4%2FBZgVdxPvSQCEHP2O" ] }'

const casos: Array<[string, string]> = [
  [CRU, 'código 404'],
  ['Cannot find channel "latest.yml" update info: HttpError: 404', 'manifesto'],
  ['getaddrinfo ENOTFOUND dito-api.defaltm.com', 'falar com o servidor'],
  ['algo que ninguem previu', 'log'],
]

for (const [entrada, esperado] of casos) {
  const saida = humanError(new Error(entrada))
  const rotulo = entrada.slice(0, 34).replace(/\s+/g, ' ')
  if (!saida.includes(esperado)) falhou(`humanError("${rotulo}...") deu "${saida}", esperava conter "${esperado}"`)
  // Nenhum pedaco do protocolo pode chegar na tela, seja qual for o erro.
  else if (/method:|Headers:|url: http|set-cookie|_gh_sess/i.test(saida)) falhou(`humanError vazou protocolo: "${saida}"`)
  else ok(`erro vira frase: "${saida}"`)
}

process.exit(falhas ? 1 : 0)
