// Publishes the release. Exists because v2.0.1 and v2.0.2 shipped with the installer alone, and
// without the channel file attached electron-updater breaks right after finding the version.
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = join(import.meta.dirname, '..')
const REPO = 'luis1amaral/dito-app'

function die(msg) {
  console.error('FALHA: ' + msg)
  process.exit(1)
}

function gh(args, { quiet = false } = {}) {
  return execFileSync('gh', args, {
    cwd: ROOT,
    encoding: 'utf8',
    stdio: quiet ? ['ignore', 'pipe', 'pipe'] : ['ignore', 'pipe', 'inherit'],
  })
}

function git(args) {
  return execFileSync('git', args, { cwd: ROOT, encoding: 'utf8' }).trim()
}

const { version } = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'))
const tag = 'v' + version
const dist = join(ROOT, 'dist')

// One platform per run: each machine publishes its own binary into the same release.
const TARGETS = {
  win32: {
    label: 'Windows',
    installer: `dito-${version}-setup.exe`,
    channelFile: 'latest.yml',
    extra: [`dito-${version}-setup.exe.blockmap`],
    packScript: 'npm run pack',
  },
  linux: {
    label: 'Linux',
    installer: `dito-${version}-amd64.deb`,
    channelFile: 'latest-linux.yml',
    extra: [],
    packScript: 'npm run pack:linux',
  },
}

const target = TARGETS[process.platform]
if (!target) die(`plataforma ${process.platform} não publica release — rode no Windows ou no Linux`)

const files = [target.installer, ...target.extra, target.channelFile].map((n) => join(dist, n))

for (const f of files) {
  if (!existsSync(f)) die(`falta ${f} — rode "${target.packScript}" antes`)
  if (statSync(f).size === 0) die(`${f} está vazio`)
}

// The channel file is the manifest the app reads: describing another version offers what does not
// exist, and naming another file downloads bytes the app then refuses.
const manifest = readFileSync(join(dist, target.channelFile), 'utf8')
const manifestVersion = /^version:\s*(.+)$/m.exec(manifest)?.[1]?.trim()
if (manifestVersion !== version)
  die(`${target.channelFile} diz ${manifestVersion}, package.json diz ${version} — rode "${target.packScript}"`)
if (!manifest.includes(target.installer))
  die(`${target.channelFile} não aponta para o instalador desta versão (${target.installer})`)

// Publishing a binary whose source is not on the remote leaves the release with no matching commit.
if (git(['status', '--porcelain'])) die('árvore suja — comite antes de publicar')
git(['fetch', '--tags', '--quiet', 'origin'])
if (git(['rev-parse', 'HEAD']) !== git(['rev-parse', '@{u}'])) die('HEAD não está no remoto — dê push antes')

// The notes come from the CHANGELOG: a release with no entry is a change with no record.
const changelog = readFileSync(join(ROOT, 'CHANGELOG.md'), 'utf8')
const block = changelog
  .split(/^## /m)
  .find((b) => b.startsWith(version + ' ') || b.startsWith(version + '\n'))
const notes = block?.split('\n').slice(1).join('\n').replace(/\n*---\s*$/, '').trim()
if (!notes) die(`CHANGELOG.md não tem a seção "## ${version}"`)

let exists = true
try {
  gh(['release', 'view', tag, '--repo', REPO, '--json', 'tagName'], { quiet: true })
} catch {
  exists = false
}

if (exists) {
  console.log(`release ${tag} já existe — subindo os assets de ${target.label} com --clobber`)
  gh(['release', 'upload', tag, ...files, '--repo', REPO, '--clobber'])
} else {
  console.log(`criando release ${tag} com os assets de ${target.label}`)
  gh(['release', 'create', tag, ...files, '--repo', REPO, '--title', `Dito ${version}`, '--notes', notes])
}

// Proof the release ended up complete, instead of trusting the upload's exit code.
const published = JSON.parse(gh(['release', 'view', tag, '--repo', REPO, '--json', 'assets'], { quiet: true }))
const names = published.assets.filter((a) => a.state === 'uploaded').map((a) => a.name)
const missing = files.map((f) => f.split(/[\\/]/).pop()).filter((n) => !names.includes(n))
if (missing.length) die('release publicada sem: ' + missing.join(', '))

console.log(`${tag} publicada com ${names.length} assets: ${names.join(', ')}`)
