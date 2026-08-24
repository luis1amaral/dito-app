// Publica a release. Existe porque a v2.0.1 e a v2.0.2 saíram só com o .exe, e sem o latest.yml
// anexado o electron-updater quebra logo depois de achar a versão. Ver docs/decisoes.md.
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const RAIZ = join(import.meta.dirname, '..')
const REPO = 'luis1amaral/dito-app'

function morrer(msg) {
  console.error('FALHA: ' + msg)
  process.exit(1)
}

function gh(args, { silencioso = false } = {}) {
  return execFileSync('gh', args, {
    cwd: RAIZ,
    encoding: 'utf8',
    stdio: silencioso ? ['ignore', 'pipe', 'pipe'] : ['ignore', 'pipe', 'inherit'],
  })
}

function git(args) {
  return execFileSync('git', args, { cwd: RAIZ, encoding: 'utf8' }).trim()
}

const { version } = JSON.parse(readFileSync(join(RAIZ, 'package.json'), 'utf8'))
const tag = 'v' + version
const dist = join(RAIZ, 'dist')

const arquivos = [
  join(dist, `dito-${version}-setup.exe`),
  join(dist, `dito-${version}-setup.exe.blockmap`),
  join(dist, 'latest.yml'),
]

for (const f of arquivos) {
  if (!existsSync(f)) morrer(`falta ${f} — rode "npm run pack" antes`)
  if (statSync(f).size === 0) morrer(`${f} está vazio`)
}

// O latest.yml é o manifesto que o app lê: se ele descrever outra versão, o updater oferece o que
// não existe.
const manifesto = readFileSync(join(dist, 'latest.yml'), 'utf8')
const versaoManifesto = /^version:\s*(.+)$/m.exec(manifesto)?.[1]?.trim()
if (versaoManifesto !== version)
  morrer(`latest.yml diz ${versaoManifesto}, package.json diz ${version} — rode "npm run pack"`)
if (!manifesto.includes(`dito-${version}-setup.exe`))
  morrer('latest.yml não aponta para o instalador desta versão')

// Publicar um binário cujo fonte não está no remoto deixa a release sem commit correspondente.
if (git(['status', '--porcelain'])) morrer('árvore suja — comite antes de publicar')
git(['fetch', '--tags', '--quiet', 'origin'])
if (git(['rev-parse', 'HEAD']) !== git(['rev-parse', '@{u}'])) morrer('HEAD não está no remoto — dê push antes')

// As notas saem do CHANGELOG: release sem entrada no changelog é mudança sem registro.
const changelog = readFileSync(join(RAIZ, 'CHANGELOG.md'), 'utf8')
const bloco = changelog
  .split(/^## /m)
  .find((b) => b.startsWith(version + ' ') || b.startsWith(version + '\n'))
const notas = bloco?.split('\n').slice(1).join('\n').replace(/\n*---\s*$/, '').trim()
if (!notas) morrer(`CHANGELOG.md não tem a seção "## ${version}"`)

let existe = true
try {
  gh(['release', 'view', tag, '--repo', REPO, '--json', 'tagName'], { silencioso: true })
} catch {
  existe = false
}

if (existe) {
  console.log(`release ${tag} já existe — subindo os assets com --clobber`)
  gh(['release', 'upload', tag, ...arquivos, '--repo', REPO, '--clobber'])
} else {
  console.log(`criando release ${tag}`)
  gh(['release', 'create', tag, ...arquivos, '--repo', REPO, '--title', `Dito ${version}`, '--notes', notas])
}

// Prova de que a release ficou completa, em vez de confiar no exit code do upload.
const publicados = JSON.parse(gh(['release', 'view', tag, '--repo', REPO, '--json', 'assets'], { silencioso: true }))
const nomes = publicados.assets.filter((a) => a.state === 'uploaded').map((a) => a.name)
const faltando = arquivos.map((f) => f.split(/[\\/]/).pop()).filter((n) => !nomes.includes(n))
if (faltando.length) morrer('release publicada sem: ' + faltando.join(', '))

console.log(`${tag} publicada com ${nomes.length} assets: ${nomes.join(', ')}`)
