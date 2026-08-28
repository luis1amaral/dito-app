// Cuts a take into decodable windows; window size and cut rule in _docs/decisoes.md.
const SAMPLE_RATE = 16000
const WINDOW_SECONDS = 8
const SPLIT_SEARCH_SECONDS = 2
const ENERGY_WINDOW_SECONDS = 0.1

const WINDOW = WINDOW_SECONDS * SAMPLE_RATE
const SEARCH = SPLIT_SEARCH_SECONDS * SAMPLE_RATE
const ENERGY = Math.round(ENERGY_WINDOW_SECONDS * SAMPLE_RATE)

function rms(samples: Float32Array, from: number, length: number): number {
  let sum = 0
  const end = Math.min(from + length, samples.length)
  for (let i = from; i < end; i += 1) sum += samples[i]! * samples[i]!
  return Math.sqrt(sum / Math.max(1, end - from))
}

// Cuts at the quietest 100 ms probe; why that size in _docs/decisoes.md.
function splitPoint(samples: Float32Array): number {
  const searchStart = Math.max(0, WINDOW - SEARCH)
  let bestIndex = WINDOW
  let bestEnergy = Infinity
  for (let i = searchStart; i + ENERGY <= WINDOW; i += Math.floor(ENERGY / 2)) {
    const energy = rms(samples, i, ENERGY)
    if (energy < bestEnergy) {
      bestEnergy = energy
      bestIndex = i + Math.floor(ENERGY / 2)
    }
  }
  // Never return 0: a zero-length cut would loop forever.
  return Math.max(1, Math.min(bestIndex, WINDOW))
}

export class AudioChunker {
  private buffered: Float32Array[] = []
  private length = 0

  /** Adds audio and returns every window that closed, already cut on silence. */
  push(samples: Float32Array): Float32Array[] {
    this.buffered.push(samples)
    this.length += samples.length
    const ready: Float32Array[] = []
    while (this.length >= WINDOW) {
      const all = this.merge()
      const cut = splitPoint(all)
      ready.push(all.subarray(0, cut))
      const rest = all.slice(cut)
      this.buffered = [rest]
      this.length = rest.length
    }
    return ready
  }

  /** The tail at the end of the take; shorter than a window by construction. */
  flush(): Float32Array | null {
    if (this.length === 0) return null
    const all = this.merge()
    this.buffered = []
    this.length = 0
    return all
  }

  reset(): void {
    this.buffered = []
    this.length = 0
  }

  private merge(): Float32Array {
    if (this.buffered.length === 1) return this.buffered[0]!
    const all = new Float32Array(this.length)
    let offset = 0
    for (const part of this.buffered) {
      all.set(part, offset)
      offset += part.length
    }
    this.buffered = [all]
    return all
  }
}
