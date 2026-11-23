import { DateTime } from 'luxon'
import { useId, useRef, useState } from 'react'
import type { Place, RoutesRequest } from '../api/types'
import { LOAD_MAX_LB, LOAD_MIN_LB } from '../lib/limits'
import { SAMPLE_TRIPS, type SampleTrip } from '../lib/samples'
import { departureWindow, nextFullHour, zoneLabel, type Clock } from '../lib/time'
import { validateTrip, type TripErrors } from '../lib/validateTrip'
import { PlaceField } from './PlaceField'

export const DEFAULT_LOAD_LB = 42000

interface Props {
  onSubmit: (request: RoutesRequest) => void
  /** Field messages from the server (e.g. a rule the browser cannot check). */
  serverErrors?: Partial<Record<keyof TripErrors, string>>
  now?: Clock
  initial?: { origin: Place; destination: Place; departure: string; load: number }
}

export function TripForm({ onSubmit, serverErrors, now = () => DateTime.now(), initial }: Props) {
  const id = useId()
  const [origin, setOrigin] = useState<Place | null>(initial?.origin ?? null)
  const [destination, setDestination] = useState<Place | null>(initial?.destination ?? null)
  // Until the user types their own time, the departure is the next full hour at the origin.
  const [typedDeparture, setTypedDeparture] = useState<string | null>(initial?.departure ?? null)
  const [load, setLoad] = useState(String(initial?.load ?? DEFAULT_LOAD_LB))
  const [showErrors, setShowErrors] = useState(false)
  const firstError = useRef<HTMLDivElement>(null)

  const departure = typedDeparture ?? (origin?.tz ? nextFullHour(origin.tz, now()) : '')

  const check = validateTrip({ origin, destination, departure, load }, now())
  const errors = { ...(showErrors ? check.errors : {}), ...serverErrors }
  const zone = origin?.tz ?? null
  const window = zone ? departureWindow(zone, now()) : null

  function submitRequest(request: RoutesRequest) {
    setShowErrors(false)
    onSubmit(request)
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setShowErrors(true)
    if (check.request) submitRequest(check.request)
    else firstError.current?.focus()
  }

  function runSample(trip: SampleTrip) {
    // One click: fill everything with defaults and search straight away.
    const tz = trip.origin.tz ?? 'America/Chicago'
    const departureTime = nextFullHour(tz, now())
    setOrigin(trip.origin)
    setDestination(trip.destination)
    setTypedDeparture(null)
    const result = validateTrip(
      { origin: trip.origin, destination: trip.destination, departure: departureTime, load },
      now(),
    )
    if (result.request) submitRequest(result.request)
    else setShowErrors(true)
  }

  function swap() {
    setOrigin(destination)
    setDestination(origin)
    setTypedDeparture(null) // the new origin may be in another time zone
  }

  const departureLabel = zone
    ? `Departure (${zoneLabel(zone, now())})`
    : "Departure (origin's local time)"

  return (
    <form onSubmit={submit} noValidate aria-label="Plan a trip" className="space-y-3">
      <div ref={firstError} tabIndex={-1} className="outline-none">
        <PlaceField label="Origin" value={origin} onChange={setOrigin} error={errors.origin} />
      </div>

      <div className="flex justify-center">
        <button
          type="button"
          onClick={swap}
          aria-label="Swap origin and destination"
          className="rounded-full border border-line px-3 py-1 text-sm hover:bg-black/5 focus:ring-2 focus:ring-accent/40 focus:outline-none"
        >
          ⇅
        </button>
      </div>

      <PlaceField
        label="Destination"
        value={destination}
        onChange={setDestination}
        error={errors.destination}
      />

      <div>
        <label htmlFor={`${id}-departure`} className="mb-1 block text-sm font-medium">
          {departureLabel}
        </label>
        <input
          id={`${id}-departure`}
          type="datetime-local"
          value={departure}
          min={window?.min}
          max={window?.max}
          onChange={(event) => setTypedDeparture(event.target.value)}
          aria-invalid={errors.departure ? true : undefined}
          aria-describedby={errors.departure ? `${id}-departure-error` : undefined}
          className="w-full rounded-md border border-line px-3 py-2 text-sm focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none aria-[invalid=true]:border-severe"
        />
        {errors.departure && (
          <p id={`${id}-departure-error`} role="alert" className="mt-1 text-xs text-severe">
            {errors.departure}
          </p>
        )}
      </div>

      <div>
        <label htmlFor={`${id}-load`} className="mb-1 block text-sm font-medium">
          Cargo weight (lb)
        </label>
        <input
          id={`${id}-load`}
          type="number"
          inputMode="numeric"
          min={LOAD_MIN_LB}
          max={LOAD_MAX_LB}
          step={500}
          value={load}
          onChange={(event) => setLoad(event.target.value)}
          aria-invalid={errors.load ? true : undefined}
          aria-describedby={`${id}-load-help`}
          className="w-full rounded-md border border-line px-3 py-2 text-sm focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none aria-[invalid=true]:border-severe"
        />
        <p id={`${id}-load-help`} className="mt-1 text-xs">
          {errors.load ? (
            <span role="alert" className="text-severe">
              {errors.load}
            </span>
          ) : check.warning ? (
            <span role="note" className="text-high-text">
              {check.warning}
            </span>
          ) : (
            <span className="text-muted">
              Cargo only; the empty truck weight is added for routing.
            </span>
          )}
        </p>
      </div>

      <button
        type="submit"
        className="w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent/90 focus:ring-2 focus:ring-accent/50 focus:ring-offset-2 focus:outline-none"
      >
        Find the safest route
      </button>

      <section aria-label="Sample trips" className="border-t border-line pt-3">
        <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">
          Try a sample trip
        </h2>
        <ul className="grid grid-cols-1 gap-2">
          {SAMPLE_TRIPS.map((trip) => (
            <li key={trip.slug}>
              <button
                type="button"
                onClick={() => runSample(trip)}
                className="w-full rounded-md border border-line px-3 py-2 text-left text-sm hover:bg-black/5 focus:ring-2 focus:ring-accent/40 focus:outline-none"
              >
                <span className="block font-medium">{trip.title}</span>
                <span className="block text-xs text-muted">{trip.detail}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </form>
  )
}
