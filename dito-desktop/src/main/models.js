// Model management: download, pick, delete. Catalog (pinned revision + per-file sha256) copied
// from stablyai/orca (MIT) -- src/main/speech/model-download-catalog.ts.
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const https = require('node:https')

function huggingFaceFiles(repo, revision, specs) {
  return specs.map(([name, bytes, sha256]) => ({
    name,
    bytes,
    sha256,
    url: `https://huggingface.co/${repo}/resolve/${revision}/${encodeURIComponent(name)}?download=true`
  }))
}

const CATALOG = [
  {
    id: 'parakeet-tdt-0.6b-v3-int8',
    label: 'Parakeet TDT v3',
    description: '25 idiomas europeus, inclusive português. Pontuação e maiúsculas.',
    type: 'transducer',
    language: 'multilingual',
    streaming: false,
    modelingUnit: 'bpe',
    isDefault: true,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8',
      '2bda32ec70b097a55adaa07d9a7173915b43cc78',
      [
        ['encoder.int8.onnx', 652184281, 'acfc2b4456377e15d04f0243af540b7fe7c992f8d898d751cf134c3a55fd2247'],
        ['decoder.int8.onnx', 11845275, '179e50c43d1a9de79c8a24149a2f9bac6eb5981823f2a2ed88d655b24248db4e'],
        ['joiner.int8.onnx', 6355277, '3164c13fc2821009440d20fcb5fdc78bff28b4db2f8d0f0b329101719c0948b3'],
        ['tokens.txt', 93939, 'd58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d']
      ]
    )
  },
  {
    id: 'parakeet-tdt-0.6b-v2-int8',
    label: 'Parakeet TDT v2',
    description: 'Só inglês. Mais rápido que o v3, com precisão parecida.',
    type: 'transducer',
    language: 'en',
    streaming: false,
    modelingUnit: 'bpe',
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8',
      '1ab9323565ddb038682214b292f588070a538ce2',
      [
        ['encoder.int8.onnx', 652184296, 'a32b12d17bbbc309d0686fbbcc2987b5e9b8333a7da83fa6b089f0a2acd651ab'],
        ['decoder.int8.onnx', 7257753, 'b6bb64963457237b900e496ee9994b59294526439fbcc1fecf705b31a15c6b4e'],
        ['joiner.int8.onnx', 1739080, '7946164367946e7f9f29a122407c3252b680dbae9a51343eb2488d057c3c43d2'],
        ['tokens.txt', 9384, 'ec182b70dd42113aff6c5372c75cac58c952443eb22322f57bbd7f53977d497d']
      ]
    )
  },
  {
    id: 'zipformer-bilingual-zh-en',
    label: 'Zipformer Bilíngue',
    description: 'Chinês e inglês, com troca de idioma no meio da frase.',
    type: 'transducer',
    language: 'zh-en',
    streaming: true,
    modelingUnit: 'cjkchar+bpe',
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20',
      '98590b7ed6443e77b714204da2757d75e1a642f4',
      [
        ['encoder-epoch-99-avg-1.onnx', 330083505, '709f0ed53a734b7942f170127e7547b566cb29c4afc5e67719f314c3d63ccb10'],
        ['decoder-epoch-99-avg-1.onnx', 13876452, '2e3b5ec371f8899ee6acd829fd753ba45772df57a91bdf37cde3136354e7db7d'],
        ['joiner-epoch-99-avg-1.onnx', 12833618, '5f2adc585dd1bec6421c8bb8660d2a73fc8b9ceb24491ef51399ba2a2f0fc31b'],
        ['tokens.txt', 56317, 'a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3'],
        ['bpe.vocab', 12564, 'd0b642f3a2eacd5fadefdeff9e0e1358cab729647cbb7fe58cf738e1f7407029']
      ]
    )
  },
  {
    id: 'paraformer-bilingual-zh-en',
    label: 'Paraformer Bilíngue',
    description: 'Chinês (mandarim e dialetos) e inglês.',
    type: 'paraformer',
    language: 'zh-en',
    streaming: true,
    modelingUnit: null,
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en',
      '8e40c43232a1c5c66c82111efc5820d3accca11b',
      [
        ['encoder.int8.onnx', 165462184, '81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a'],
        ['decoder.int8.onnx', 71664561, 'f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f'],
        ['tokens.txt', 75756, '59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6']
      ]
    )
  },
  {
    id: 'zipformer-streaming-en-20m',
    label: 'Zipformer EN 20M',
    description: 'Só inglês. Leve (20M), bom equilíbrio entre velocidade e tamanho.',
    type: 'transducer',
    language: 'en',
    streaming: true,
    modelingUnit: 'bpe',
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17',
      'd42f2d9f7ca24806fb667456a18a9f1b60f70d16',
      [
        ['encoder-epoch-99-avg-1.onnx', 88804590, 'f77a22f4ff94604e1afb2aeb13504d7699363528c047c97d3436087c95c9b659'],
        ['decoder-epoch-99-avg-1.onnx', 2092272, '45a7f940ecfb53d89fa270ad11b88b961e53a317203eb24b1c8e95ed208b0f30'],
        ['joiner-epoch-99-avg-1.onnx', 1026462, '343e17dffa4f386ca206e00d3c406908f68f473c3d35968d6c3cddd5b8559a94'],
        ['tokens.txt', 5048, '49e3c2646595fd907228b3c6787069658f67b17377c60aeb8619c4551b2316fb']
      ]
    )
  },
  {
    id: 'zipformer-streaming-zh-14m',
    label: 'Zipformer ZH 14M',
    description: 'Só chinês. Ultraleve (14M), para máquina fraca.',
    type: 'transducer',
    language: 'zh',
    streaming: true,
    modelingUnit: 'cjkchar',
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23',
      '204ad334e2e683fd295359930cc16fc0432a23ac',
      [
        ['encoder-epoch-99-avg-1.onnx', 40948171, '84c6a8f372686faa5b8f45f2d79f0816f76dcd9f547acb9a90eba2772d7eda8b'],
        ['decoder-epoch-99-avg-1.onnx', 7509745, '5ee0f03a2768ff1d5c83ef3a493243c7935d316cd41280037b14783a3467cc78'],
        ['joiner-epoch-99-avg-1.onnx', 7109975, '030212efaea9a8b6a4fa98faf6ac6055529c4408cf4865e898220ddd02780f34'],
        ['tokens.txt', 48697, '8b294db9045d6e5f94647f4c1eec1af4da143a75053c399611444b378ff966ac']
      ]
    )
  },
  {
    id: 'zipformer-streaming-korean',
    label: 'Zipformer Coreano',
    description: 'Só coreano.',
    type: 'transducer',
    language: 'ko',
    streaming: true,
    modelingUnit: 'bpe',
    isDefault: false,
    files: huggingFaceFiles(
      'k2-fsa/sherpa-onnx-streaming-zipformer-korean-2024-06-16',
      'ba6078bca4daf3f0dd37f79d0ab505af71df14a6',
      [
        ['encoder-epoch-99-avg-1.int8.onnx', 126968852, '8d0b1aa24fbedd4e3948564ab7facd151b8ce9b0c48fc987c541de2de3af5697'],
        ['decoder-epoch-99-avg-1.int8.onnx', 2844692, '68ea197936aabd249f38b53a87c775422bca64428ad4427d0e6e8092593e71fb'],
        ['joiner-epoch-99-avg-1.int8.onnx', 2581421, '128b80a66a1f718488af8560f9d15895109b99ff3e573f0a0130e03774ef1ced'],
        ['tokens.txt', 60246, '016bdf0965029263b7ad01b742366ee542ef0bef38261510e8176ff6f2e9e668']
      ]
    )
  },
  {
    id: 'parakeet-tdt-ctc-0.6b-ja-int8',
    label: 'Parakeet TDT-CTC JA',
    description: 'Só japonês. Treinado em 35 mil horas, com pontuação.',
    type: 'nemo-ctc',
    language: 'ja',
    streaming: false,
    modelingUnit: null,
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-nemo-parakeet-tdt_ctc-0.6b-ja-35000-int8',
      'bef18eb066808c90bd0f5df5be685767b0732de8',
      [
        ['model.int8.onnx', 655542604, '3addd00ef5bd1742078389e540b77394e4a508bdf2f4c9ad1b4a76d93e76598e'],
        ['tokens.txt', 28557, '732f64c53909f2620c713f4106b487d92e6f54a6915b3cd3d1dbd32f9f4f392a']
      ]
    )
  },
  {
    id: 'whisper-tiny',
    label: 'Whisper Tiny',
    description: 'Mais de 90 idiomas. Menos preciso que o Parakeet, mas cobre mais idiomas.',
    type: 'whisper',
    language: 'multilingual',
    streaming: false,
    modelingUnit: null,
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-whisper-tiny',
      '65176e2deb88badc814a94058666cadccc29b61c',
      [
        ['tiny-encoder.onnx', 37647080, '42c1d4cbf889632ba21ab6f0d4064c80209755f265ce5cd630db4a6793e7089c'],
        ['tiny-decoder.onnx', 114505801, 'e144c07dc6b55cece24392811f2d934b97013811f5e677d1315d341a0a74a25d'],
        ['tiny-tokens.txt', 816730, 'b34b360dbb493e781e479794586d661700670d65564001f23024971d1f2fa126']
      ]
    )
  },
  {
    id: 'sense-voice-zh-en-ja-ko-yue',
    label: 'SenseVoice',
    description: 'Chinês, inglês, japonês, coreano e cantonês, com detecção automática.',
    type: 'senseVoice',
    language: 'multilingual',
    streaming: false,
    modelingUnit: null,
    isDefault: false,
    files: huggingFaceFiles(
      'csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17',
      '2365baeacb507f821a0c8120fcee3d484dba7a07',
      [
        ['model.int8.onnx', 239233841, 'c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51'],
        ['tokens.txt', 315894, 'f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc']
      ]
    )
  }
]

const DEFAULT_MODEL = CATALOG.find((m) => m.isDefault)

function baseDir(appData) {
  return path.join(appData, 'dito', 'speech-models')
}

function dirFor(appData, id) {
  return path.join(baseDir(appData), id)
}

// Installed means every catalog file is on disk at its exact size: models name files differently
// (encoder.int8.onnx vs tiny-encoder.onnx vs encoder-epoch-99-avg-1.onnx), so the list is the truth.
function isInstalled(appData, id) {
  const model = CATALOG.find((m) => m.id === id)
  if (!model) return false
  const dir = dirFor(appData, id)
  return model.files.every((f) => {
    const file = path.join(dir, f.name)
    return fs.existsSync(file) && fs.statSync(file).size === f.bytes
  })
}

function list(appData, activeId) {
  const installed = CATALOG.filter((m) => isInstalled(appData, m.id))
  return CATALOG.map((m) => ({
    id: m.id,
    label: m.label,
    description: m.description,
    language: m.language,
    type: m.type,
    streaming: m.streaming,
    isDefault: !!m.isDefault,
    bytes: m.files.reduce((s, f) => s + f.bytes, 0),
    installed: isInstalled(appData, m.id),
    active: m.id === activeId,
    // Never leave the user with no model: deleting requires a spare.
    canDelete: isInstalled(appData, m.id) && installed.length > 1
  }))
}

function sha256Of(file) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256')
    fs.createReadStream(file)
      .on('data', (d) => h.update(d))
      .on('end', () => resolve(h.digest('hex')))
      .on('error', reject)
  })
}

function downloadFile(url, dest, onProgress) {
  return new Promise((resolve, reject) => {
    const partial = dest + '.partial'
    const out = fs.createWriteStream(partial)
    const request = (address, hops) => {
      if (hops > 5) return reject(new Error('too many redirects'))
      https.get(address, { headers: { 'User-Agent': 'dito' } }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          res.resume()
          return request(res.headers.location, hops + 1)
        }
        if (res.statusCode !== 200) {
          res.resume()
          return reject(new Error(`HTTP ${res.statusCode} on ${address}`))
        }
        let read = 0
        res.on('data', (d) => {
          read += d.length
          if (onProgress) onProgress(read)
        })
        res.pipe(out)
        out.on('finish', () => out.close(() => {
          // Only becomes the real file once closed, so a partial is never mistaken for done.
          fs.renameSync(partial, dest)
          resolve()
        }))
      }).on('error', (e) => {
        try { fs.unlinkSync(partial) } catch {}
        reject(e)
      })
    }
    request(url, 0)
  })
}

async function download(appData, id, onProgress) {
  const model = CATALOG.find((m) => m.id === id)
  if (!model) throw new Error('unknown model: ' + id)
  const dir = dirFor(appData, id)
  fs.mkdirSync(dir, { recursive: true })

  const totalBytes = model.files.reduce((s, f) => s + f.bytes, 0)
  let doneBytes = 0

  for (const file of model.files) {
    const dest = path.join(dir, file.name)
    if (fs.existsSync(dest) && fs.statSync(dest).size === file.bytes) {
      doneBytes += file.bytes
      if (onProgress) onProgress({ id, file: file.name, done: doneBytes, total: totalBytes })
      continue
    }
    const base = doneBytes
    await downloadFile(file.url, dest, (read) => {
      if (onProgress) onProgress({ id, file: file.name, done: base + read, total: totalBytes })
    })
    // A truncated download passes the size check and breaks the engine later; the hash catches it.
    const hash = await sha256Of(dest)
    if (hash !== file.sha256) {
      fs.unlinkSync(dest)
      throw new Error(`${file.name}: sha256 mismatch`)
    }
    doneBytes += file.bytes
  }
  return dir
}

function remove(appData, id) {
  const installed = CATALOG.filter((m) => isInstalled(appData, m.id))
  if (!isInstalled(appData, id)) throw new Error('esse modelo não está instalado')
  if (installed.length <= 1) {
    throw new Error('é o único modelo instalado — baixe outro antes de apagar este')
  }
  fs.rmSync(dirFor(appData, id), { recursive: true, force: true })
  return installed.filter((m) => m.id !== id)[0].id
}

// First run: copying from a local copy (Orca ships the same model) beats a 670 MB download.
async function ensureDefault(appData, onProgress, onNotice) {
  if (CATALOG.some((m) => isInstalled(appData, m.id))) return null
  const dest = dirFor(appData, DEFAULT_MODEL.id)
  const fromOrca = path.join(appData, 'orca', 'speech-models', DEFAULT_MODEL.id)
  if (fs.existsSync(path.join(fromOrca, 'encoder.int8.onnx'))) {
    if (onNotice) onNotice('copying a local copy of the default model')
    fs.mkdirSync(dest, { recursive: true })
    for (const name of fs.readdirSync(fromOrca)) {
      fs.copyFileSync(path.join(fromOrca, name), path.join(dest, name))
    }
    return dest
  }
  if (onNotice) onNotice('downloading the default model')
  return download(appData, DEFAULT_MODEL.id, onProgress)
}

module.exports = { CATALOG, DEFAULT_MODEL, dirFor, isInstalled, list, download, remove, ensureDefault }
