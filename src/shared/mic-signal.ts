// Tells a dead input from a person pausing; why rms alone cannot do it is in docs/decisoes.md.

/** A block only counts as nothing arriving when it is digitally null, not merely quiet. */
export const DEAD_INPUT_MS = 2000

/** The device can hand out null blocks while it wakes from suspend; that is not a failure. */
export const WARMUP_MS = 1200

export class MicSignalWatch {
  private startedAt = 0
  private deadSince = 0

  start(now: number): void {
    this.startedAt = now
    this.deadSince = 0
  }

  /** True while the input has been delivering nothing at all for DEAD_INPUT_MS straight. */
  isDead(rms: number, now: number): boolean {
    if (rms > 0) {
      this.deadSince = 0
      return false
    }
    if (now - this.startedAt < WARMUP_MS) return false
    if (!this.deadSince) {
      this.deadSince = now
      return false
    }
    return now - this.deadSince >= DEAD_INPUT_MS
  }
}
