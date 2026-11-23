import { describe, expect, it } from 'vitest'
import { PLAY_DURATION_MS, REDUCED_STEP_MS, createPlayer } from '../../src/lib/play'

function setup(startHour = 0, reducedMotion = false, last = 48) {
  const state = { hour: startHour, playing: true, hours: [] as number[] }
  const store = {
    getState: () => ({
      hour: state.hour,
      setHour: (h: number) => {
        state.hour = h
        state.hours.push(h)
      },
      setPlaying: (p: boolean) => {
        state.playing = p
      },
    }),
  }
  let callback: ((now: number) => void) | null = null
  let cancelled = 0
  const player = createPlayer({
    store,
    last,
    reducedMotion,
    frame: (cb) => {
      callback = cb
      return 1
    },
    cancel: () => {
      cancelled += 1
      callback = null
    },
  })
  const advance = (now: number) => {
    const cb = callback
    callback = null
    cb?.(now)
  }
  return { state, player, advance, cancelled: () => cancelled, running: () => callback !== null }
}

describe('createPlayer', () => {
  it('runs the whole window in about ten seconds, smoothly', () => {
    const t = setup()
    t.player.start()
    t.advance(1000) // the first frame sets the origin
    t.advance(1000 + PLAY_DURATION_MS / 2)
    expect(t.state.hour).toBeCloseTo(24, 5) // halfway, with a fraction allowed
    t.advance(1000 + PLAY_DURATION_MS * 0.26)
    expect(t.state.hour % 1).not.toBe(0)
    t.advance(1000 + PLAY_DURATION_MS)
    expect(t.state.hour).toBe(48)
    expect(t.state.playing).toBe(false)
    expect(t.running()).toBe(false)
  })

  it('restarts from the beginning when started at the end', () => {
    const t = setup(48)
    t.player.start()
    t.advance(0)
    t.advance(PLAY_DURATION_MS / 4)
    expect(t.state.hour).toBeCloseTo(12, 5)
  })

  it('continues from the current hour', () => {
    const t = setup(30)
    t.player.start()
    t.advance(0)
    t.advance(PLAY_DURATION_MS / 4)
    expect(t.state.hour).toBeCloseTo(42, 5)
  })

  it('moves in whole hours when motion is reduced', () => {
    const t = setup(0, true)
    t.player.start()
    t.advance(0)
    t.advance(REDUCED_STEP_MS * 3 + 10)
    t.advance(REDUCED_STEP_MS * 5 + 10)
    expect(t.state.hours.every((h) => Number.isInteger(h))).toBe(true)
    expect(t.state.hour).toBe(5)
  })

  it('stops when asked', () => {
    const t = setup()
    t.player.start()
    t.advance(0)
    t.player.stop()
    expect(t.running()).toBe(false)
    expect(t.cancelled()).toBeGreaterThan(0)
  })
})
