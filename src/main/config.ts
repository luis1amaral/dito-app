import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { DEFAULT_CONFIG, migrate, type Config } from '../shared/config'
import { CONFIG_FILE, DATA_DIR } from './paths'
import { log } from './logger'

let current: Config = load()

function load(): Config {
  try {
    return migrate(JSON.parse(readFileSync(CONFIG_FILE, 'utf8')) as Record<string, unknown>)
  } catch {
    return { ...DEFAULT_CONFIG }
  }
}

export function get(): Config {
  return current
}

export function update(patch: Partial<Config>): Config {
  current = migrate({ ...current, ...patch } as Record<string, unknown>)
  mkdirSync(DATA_DIR, { recursive: true })
  writeFileSync(CONFIG_FILE, JSON.stringify(current, null, 2))
  log('config: ' + JSON.stringify(current))
  return current
}
