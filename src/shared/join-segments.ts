// Joins decoded windows; only the space between them is decided (_docs/decisoes.md).

const NO_SPACE_BEFORE = ',.;:!?%)]}»…'
const NO_SPACE_AFTER = '([{«'

export function joinSegment(soFar: string, next: string): string {
  const piece = next.trim()
  if (!piece) return soFar
  if (!soFar) return piece
  const last = soFar[soFar.length - 1]!
  const first = piece[0]!
  if (/\s/.test(last) || /\s/.test(first)) return soFar + piece
  if (NO_SPACE_BEFORE.includes(first)) return soFar + piece
  if (NO_SPACE_AFTER.includes(last)) return soFar + piece
  return soFar + ' ' + piece
}

/** What `next` adds to `soFar`, separator included: typing only this keeps the two in step. */
export function segmentDelta(soFar: string, next: string): string {
  return joinSegment(soFar, next).slice(soFar.length)
}
