import { appendFileSync, mkdirSync, renameSync, rmSync, statSync } from 'node:fs'
import { dirname } from 'node:path'
import { LOG_FILE } from './paths'

const MAX_BYTES = 2 * 1024 * 1024
let sinceCheck = 0

mkdirSync(dirname(LOG_FILE), { recursive: true })

// An append-only log grows until the disk complains; keep one previous file and start over.
function rotateIfBig(): void {
  try {
    if (statSync(LOG_FILE).size < MAX_BYTES) return
    rmSync(LOG_FILE + '.1', { force: true })
    renameSync(LOG_FILE, LOG_FILE + '.1')
  } catch {
    // A locked or missing log must never take the app down.
  }
}

// Synchronous on purpose: an async sink loses the last line in a segfault.
export function log(message: string): void {
  const line = new Date().toISOString() + ' ' + message + '\n'
  if ((sinceCheck += 1) % 200 === 0) rotateIfBig()
  try {
    appendFileSync(LOG_FILE, line)
  } catch {
    // Same reason as above.
  }
  process.stdout.write(line)
}
