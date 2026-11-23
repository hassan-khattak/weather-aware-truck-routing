import { useEffect, useMemo, useRef, type KeyboardEvent } from 'react'
import type { Route } from '../api/types'
import { createPlayer } from '../lib/play'
import { sliderLabel } from '../lib/time'
import { useUiStore } from '../state/uiStore'
import { toLngLat } from './routeLayers'
import { truckAt } from './truck'

const BIG_STEP_H = 6

interface Props {
  startUtc: string
  tz: string
  /** Number of forecast hours (0 to hours - 1). */
  hours: number
  route: Route | undefined
}

/**
 * The forecast slider. The input is uncontrolled and follows the store through a subscription, so
 * dragging it never re-renders this component or anything above it: only the small readout.
 */
export function TimeSlider({ startUtc, tz, hours, route }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const last = hours - 1

  useEffect(() => {
    const show = (hour: number) => {
      const el = input.current
      if (!el) return
      const whole = Math.round(hour)
      el.value = String(whole)
      el.setAttribute('aria-valuetext', sliderLabel(startUtc, whole, tz))
    }
    show(useUiStore.getState().hour)
    return useUiStore.subscribe((now, before) => {
      if (now.hour !== before.hour) show(now.hour)
    })
  }, [startUtc, tz])

  // Play runs the hour forward; the player lives outside React and only touches the store.
  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const player = createPlayer({
      store: useUiStore,
      last,
      reducedMotion: reduced,
      frame: (callback) => requestAnimationFrame(callback),
      cancel: (id) => cancelAnimationFrame(id),
    })
    if (useUiStore.getState().playing) player.start()
    const unsubscribe = useUiStore.subscribe((now, before) => {
      if (now.playing === before.playing) return
      if (now.playing) player.start()
      else player.stop()
    })
    return () => {
      unsubscribe()
      player.stop()
    }
  }, [last])

  function setHour(hour: number) {
    const { setHour, setPlaying } = useUiStore.getState()
    setPlaying(false) // touching the slider takes over from Play
    setHour(Math.min(Math.max(hour, 0), last))
  }

  // Arrows move an hour, Shift + arrow a quarter of a day; Home and End jump to the ends.
  // Handled here (not left to the browser) so every browser behaves the same.
  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    const current = Math.round(useUiStore.getState().hour)
    const direction = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[event.key]
    if (direction) {
      event.preventDefault()
      setHour(current + direction * (event.shiftKey ? BIG_STEP_H : 1))
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      setHour(event.key === 'Home' ? 0 : last)
    }
  }

  return (
    <section
      aria-label="Forecast time"
      className="absolute right-3 bottom-8 left-3 z-10 mx-auto max-w-xl rounded-lg bg-white/95 p-3 shadow-md"
    >
      <div className="flex items-center gap-2">
        <PlayButton />
        <div className="min-w-0 flex-1">
          <HourReadout startUtc={startUtc} tz={tz} last={last} route={route} />
        </div>
      </div>
      <input
        ref={input}
        type="range"
        min={0}
        max={last}
        step={1}
        defaultValue={0}
        aria-label="Hours after departure"
        onChange={(event) => setHour(Number(event.target.value))}
        onKeyDown={onKeyDown}
        className="mt-2 w-full accent-accent"
      />
    </section>
  )
}

/** The label and the truck's status; the only part that re-renders while the hour changes. */
function HourReadout({ startUtc, tz, last, route }: Omit<Props, 'hours'> & { last: number }) {
  const hour = useUiStore((s) => Math.floor(s.hour))
  const line = useMemo(() => (route ? toLngLat(route.geometry) : []), [route])
  const truck = route ? truckAt(route, line, hour * 3600, last * 3600) : undefined
  const status =
    truck?.state === 'arrived'
      ? 'Arrived'
      : truck?.state === 'beyond-window'
        ? 'Trip continues beyond forecast window'
        : truck?.state === 'parked'
          ? 'Parked: required stop'
          : null
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
      <span className="font-medium">{sliderLabel(startUtc, hour, tz)}</span>
      <span role="status" className="text-xs text-muted">
        {status}
      </span>
    </div>
  )
}

function PlayButton() {
  const playing = useUiStore((s) => s.playing)
  return (
    <button
      type="button"
      aria-pressed={playing}
      onClick={() => useUiStore.getState().setPlaying(!playing)}
      className="rounded-md border border-line px-2.5 py-1 text-sm font-medium focus:ring-2 focus:ring-accent/50 focus:outline-none"
    >
      {playing ? '⏸ Pause' : '▶ Play'}
    </button>
  )
}
