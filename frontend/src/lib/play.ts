/** How long Play takes to run the whole forecast window. */
export const PLAY_DURATION_MS = 10_000
/** With "reduce motion", Play moves one whole hour at a time at this pace. */
export const REDUCED_STEP_MS = 250

export interface PlayStore {
  getState(): { hour: number; setHour(hour: number): void; setPlaying(playing: boolean): void }
}

export interface Player {
  start(): void
  stop(): void
}

interface Options {
  store: PlayStore
  /** The last hour of the forecast window. */
  last: number
  reducedMotion: boolean
  frame: (callback: (now: number) => void) => number
  cancel: (id: number) => void
}

/**
 * Runs the hour from where it is to the end of the window: smoothly (fractional hours, so the
 * heatmap cross-fades and the truck glides) or in whole-hour steps when motion is reduced.
 * Restarts from 0 when started at the end. Stops itself at the end.
 */
export function createPlayer({ store, last, reducedMotion, frame, cancel }: Options): Player {
  let id: number | null = null

  const start = () => {
    stop()
    let hour = store.getState().hour
    if (hour >= last) hour = 0
    let origin: number | null = null
    const from = hour

    const tick = (now: number) => {
      origin ??= now
      const elapsed = now - origin
      const next = reducedMotion
        ? from + Math.floor(elapsed / REDUCED_STEP_MS)
        : from + (elapsed / PLAY_DURATION_MS) * last
      const { setHour, setPlaying } = store.getState()
      if (next >= last) {
        setHour(last)
        setPlaying(false)
        id = null
        return
      }
      setHour(next)
      id = frame(tick)
    }
    id = frame(tick)
  }

  const stop = () => {
    if (id !== null) cancel(id)
    id = null
  }

  return { start, stop }
}
