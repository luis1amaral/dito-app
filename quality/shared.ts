// Gate for the pure units of src/shared: joining segments, config migration and the i18n contract.
// They had no gate at all -- everything that guarded them was a type, and a type does not run.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { joinSegment, segmentDelta } from '../src/shared/join-segments'
import { DEFAULT_CONFIG, HOTKEYS, MODES, migrate } from '../src/shared/config'
import { LANGS, t, type MessageKey } from '../src/shared/i18n'

const ROOT = join(import.meta.dirname, '..')
const SCREENS = join(ROOT, 'src', 'renderer')

let failures = 0

function check(name: string, got: unknown, expected: unknown): void {
  const ok = JSON.stringify(got) === JSON.stringify(expected)
  if (ok) {
    console.log('  ok   ' + name)
  } else {
    console.log(`  FALHA ${name} · esperado ${JSON.stringify(expected)}, veio ${JSON.stringify(got)}`)
    failures += 1
  }
}

console.log('-- emenda de segmentos')
check('palavra + palavra ganha espaço', joinSegment('bom', 'dia'), 'bom dia')
check('pontuação cola na palavra', joinSegment('bom dia', ', tudo bem?'), 'bom dia, tudo bem?')
check('abre parêntese cola no que vem', joinSegment('teste (', 'um)'), 'teste (um)')
check('espaço existente não vira dois', joinSegment('bom ', 'dia'), 'bom dia')
check('segmento vazio não muda nada', joinSegment('bom dia', '   '), 'bom dia')
check('primeiro segmento vem inteiro', joinSegment('', ' bom dia '), 'bom dia')
// The delta is what gets typed mid-take: dropping the separator glued words together in 2.0.9.
check('delta carrega o separador', segmentDelta('bom', 'dia'), ' dia')
check('delta de pontuação não tem espaço', segmentDelta('bom dia', ', tudo bem'), ', tudo bem')
check('delta vazio quando nada muda', segmentDelta('bom dia', ''), '')

console.log('-- migração de configuração')
check('arquivo vazio vira o padrão', migrate({}), DEFAULT_CONFIG)
check('campo pt-BR antigo migra', migrate({ tecla: 'F8' }).key, 'F8')
check('valor pt-BR antigo migra', migrate({ modo: 'segurar' }).mode, 'hold')
check('campo novo vence o antigo', migrate({ tecla: 'F8', key: 'F9' }).key, 'F9')
check('tecla fora da lista cai no padrão', migrate({ key: 'Ctrl+Q' }).key, DEFAULT_CONFIG.key)
check('modo fora da lista cai no padrão', migrate({ mode: 'gravando' }).mode, DEFAULT_CONFIG.mode)
check('idioma fora da lista cai no padrão', migrate({ lang: 'tlh' }).lang, DEFAULT_CONFIG.lang)
check('campo desconhecido não apaga o resto', migrate({ xyz: 1 }).model, DEFAULT_CONFIG.model)
check('a tecla padrão está entre as ofertadas', HOTKEYS.includes(DEFAULT_CONFIG.key), true)
check('o modo padrão está entre os ofertados', MODES.includes(DEFAULT_CONFIG.mode), true)

console.log('-- dicionário de idiomas')
// t() is the only public door into the dictionary, so the key list comes from the screens.
const dictKeys = new Set<string>()
for (const file of readdirSync(SCREENS).filter((f) => f.endsWith('.html'))) {
  const html = readFileSync(join(SCREENS, file), 'utf8')
  for (const m of html.matchAll(/data-i18n(?:-placeholder|-title)?="([^"]+)"/g)) dictKeys.add(m[1]!)
}
console.log(`  ${dictKeys.size} chave(s) usadas nas telas`)
for (const key of dictKeys) {
  for (const lang of LANGS) {
    const value = t(lang, key as MessageKey)
    if (typeof value !== 'string' || value.trim() === '') {
      console.log(`  FALHA a tela pede "${key}" e o idioma ${lang} não tem texto para ela`)
      failures += 1
    }
  }
}
if (dictKeys.size === 0) {
  console.log('  FALHA nenhuma chave encontrada nas telas — o portão passaria sem provar nada')
  failures += 1
} else {
  console.log('  ok   toda chave de tela tem texto nos dois idiomas')
}

console.log('')
if (failures) {
  console.log(`SHARED: FALHA - ${failures} reprovacao(oes)`)
  process.exit(1)
}
console.log('SHARED: PASSA')
process.exit(0)
