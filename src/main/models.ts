// Model install state, download, pick and delete; download shape in _docs/decisoes.md.
import { createHash } from 'node:crypto'
import {
  copyFileSync,
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync
} from 'node:fs'
import { get as httpsGet } from 'node:https'
import { join } from 'node:path'
import type { DownloadProgress } from '../shared/ipc'
import type { ModelManifest, ModelRow } from '../shared/models'
import { CATALOG, DEFAULT_MODEL } from './catalog'
import { MODELS_DIR } from './paths'

export { CATALOG, DEFAULT_MODEL }

export type ProgressFn = (p: DownloadProgress) => void

export function dirFor(id: string): string {
  return join(MODELS_DIR, id)
}

function manifest(id: string): ModelManifest | undefined {
  return CATALOG.find((m) => m.id === id)
}

// Every catalog file at its exact size; models name files differently (_docs/decisoes.md).
export function isInstalled(id: string): boolean {
  const model = manifest(id)
  if (!model) return false
  const dir = dirFor(id)
  return model.files.every((f) => {
    const file = join(dir, f.name)
    return existsSync(file) && statSync(file).size === f.bytes
  })
}

export function installed(): ModelManifest[] {
  return CATALOG.filter((m) => isInstalled(m.id))
}

export function list(activeId: string): ModelRow[] {
  const count = installed().length
  return CATALOG.map((m) => ({
    id: m.id,
    label: m.label,
    description: m.description,
    language: m.language,
    type: m.type,
    streaming: m.streaming,
    isDefault: m.isDefault,
    bytes: m.files.reduce((s, f) => s + f.bytes, 0),
    installed: isInstalled(m.id),
    active: m.id === activeId,
    // Never leave the user with no model: deleting requires a spare.
    canDelete: isInstalled(m.id) && count > 1
  }))
}

function sha256Of(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const h = createHash('sha256')
    createReadStream(file)
      .on('data', (d) => h.update(d))
      .on('end', () => resolve(h.digest('hex')))
      .on('error', reject)
  })
}

const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 15000]
const MAX_STALLED_ATTEMPTS = 5
const MAX_ATTEMPTS = 40

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

function bytesOnDisk(file: string): number {
  try {
    return statSync(file).size
  } catch {
    return 0
  }
}

type MaybeRetryable = Error & { retryable?: boolean; code?: string }

function isRetryable(err: MaybeRetryable): boolean {
  if (err.retryable) return true
  const code = err.code ?? ''
  return ['ECONNRESET', 'ETIMEDOUT', 'ECONNREFUSED', 'EPIPE', 'ENOTFOUND', 'EAI_AGAIN'].includes(code)
}

function requestOnce(url: string, partial: string, from: number, onChunk: () => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const headers: Record<string, string> = { 'User-Agent': 'dito' }
    if (from > 0) headers.Range = 'bytes=' + from + '-'
    const go = (address: string, hops: number): void => {
      if (hops > 5) return reject(new Error('too many redirects'))
      httpsGet(address, { headers }, (res) => {
        const status = res.statusCode ?? 0
        if (status >= 300 && status < 400 && res.headers.location) {
          res.resume()
          // Hugging Face answers with a RELATIVE Location; https.get rejects it as an invalid URL.
          return go(new URL(res.headers.location, address).toString(), hops + 1)
        }
        if (status !== 200 && status !== 206) {
          res.resume()
          const err: MaybeRetryable = new Error('HTTP ' + status)
          err.retryable = status >= 500 || status === 429
          return reject(err)
        }
        // A server that ignores Range restarts the file: truncate instead of appending garbage.
        const append = from > 0 && status === 206
        const out = createWriteStream(partial, append ? { flags: 'a' } : {})
        res.on('data', onChunk)
        res.on('error', reject)
        out.on('error', reject)
        res.pipe(out)
        out.on('finish', () => out.close(() => resolve()))
      }).on('error', reject)
    }
    go(url, 0)
  })
}

// Range-resume, canonical URL, size on disk, stall counter: why each in _docs/decisoes.md.
async function downloadFile(url: string, dest: string, expected: number, onBytes: (n: number) => void): Promise<void> {
  const partial = dest + '.partial'
  let stalled = 0
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const from = bytesOnDisk(partial)
    if (from === expected) break
    if (from > expected) rmSync(partial, { force: true })
    try {
      await requestOnce(url, partial, bytesOnDisk(partial), () => onBytes(bytesOnDisk(partial)))
    } catch (err) {
      if (!isRetryable(err as MaybeRetryable)) throw err
    }
    const now = bytesOnDisk(partial)
    if (now === expected) break
    stalled = now > from ? 0 : stalled + 1
    if (stalled >= MAX_STALLED_ATTEMPTS) {
      throw new Error('download parou em ' + now + ' de ' + expected + ' bytes')
    }
    await sleep(RETRY_DELAYS_MS[Math.min(stalled, RETRY_DELAYS_MS.length - 1)] ?? 15000)
  }
  // Only becomes the real file once complete, so a partial is never mistaken for done.
  renameSync(partial, dest)
}

export async function download(id: string, onProgress?: ProgressFn): Promise<string> {
  const model = manifest(id)
  if (!model) throw new Error('modelo desconhecido: ' + id)
  const dir = dirFor(id)
  mkdirSync(dir, { recursive: true })

  const total = model.files.reduce((s, f) => s + f.bytes, 0)
  let done = 0

  for (const file of model.files) {
    const dest = join(dir, file.name)
    if (existsSync(dest) && statSync(dest).size === file.bytes) {
      done += file.bytes
      onProgress?.({ id, file: file.name, done, total })
      continue
    }
    const base = done
    await downloadFile(file.url, dest, file.bytes, (read) => {
      onProgress?.({ id, file: file.name, done: base + read, total })
    })
    // A truncated download passes the size check and breaks the engine later; the hash catches it.
    const hash = await sha256Of(dest)
    if (hash !== file.sha256) {
      rmSync(dest, { force: true })
      throw new Error(file.name + ': sha256 nao confere')
    }
    done += file.bytes
  }
  return dir
}

export function remove(id: string): string {
  const present = installed()
  if (!isInstalled(id)) throw new Error('esse modelo não está instalado')
  if (present.length <= 1) throw new Error('é o único modelo instalado — baixe outro antes de apagar este')
  rmSync(dirFor(id), { recursive: true, force: true })
  return present.find((m) => m.id !== id)!.id
}

// A model dropped from the catalog, or a half-written download, is hundreds of MB of silent junk.
export function sweepOrphans(): string[] {
  const known = new Set(CATALOG.map((m) => m.id))
  const removed: string[] = []
  let entries: string[] = []
  try {
    entries = readdirSync(MODELS_DIR)
  } catch {
    return removed
  }
  for (const name of entries) {
    const dir = join(MODELS_DIR, name)
    try {
      if (!statSync(dir).isDirectory()) continue
      if (known.has(name)) {
        for (const f of readdirSync(dir)) {
          if (f.endsWith('.partial')) {
            rmSync(join(dir, f), { force: true })
            removed.push(name + '/' + f)
          }
        }
        continue
      }
      rmSync(dir, { recursive: true, force: true })
      removed.push(name)
    } catch {
      // A file we cannot inspect is not worth failing the boot over.
    }
  }
  return removed
}

// First run: copying a local copy (Orca ships the same model) beats a 640 MB download.
export async function ensureDefault(
  appData: string,
  onProgress?: ProgressFn,
  onNotice?: (m: string) => void
): Promise<string | null> {
  if (installed().length > 0) return null
  const dest = dirFor(DEFAULT_MODEL.id)
  const fromOrca = join(appData, 'orca', 'speech-models', DEFAULT_MODEL.id)
  if (existsSync(join(fromOrca, 'encoder.int8.onnx'))) {
    onNotice?.('copying a local copy of the default model')
    mkdirSync(dest, { recursive: true })
    for (const name of readdirSync(fromOrca)) {
      copyFileSync(join(fromOrca, name), join(dest, name))
    }
    return dest
  }
  onNotice?.('downloading the default model')
  return download(DEFAULT_MODEL.id, onProgress)
}
