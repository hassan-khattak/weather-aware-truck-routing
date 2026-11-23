import type { DateTime } from 'luxon'
import type { Place, RoutesRequest } from '../api/types'
import { haversineMi } from './geo'
import {
  COVERAGE_MESSAGE,
  DEPARTURE_MAX_AHEAD_H,
  DEPARTURE_PAST_GRACE_MIN,
  LOAD_MAX_LB,
  LOAD_MIN_LB,
  LOAD_WARNING_LB,
  LOAD_WARNING_TEXT,
  MIN_TRIP_SEPARATION_MI,
} from './limits'
import { parseLocal } from './time'

export interface TripInput {
  origin: Place | null
  destination: Place | null
  /** Wall-clock time at the origin, "2026-11-24T15:00". */
  departure: string
  /** Cargo weight as typed. */
  load: string
}

export interface TripErrors {
  origin?: string
  destination?: string
  departure?: string
  load?: string
}

export interface TripCheck {
  errors: TripErrors
  /** Soft warning, not an error: the trip can still be searched. */
  warning?: string
  /** Present only when there are no errors. */
  request?: RoutesRequest
}

const formatLb = (n: number) => n.toLocaleString('en-US')

/** The same rules the server applies, so people see the problem before sending anything. */
export function validateTrip(input: TripInput, now: DateTime): TripCheck {
  const errors: TripErrors = {}
  const { origin, destination } = input

  if (!origin) errors.origin = 'Choose an origin from the suggestions.'
  else if (origin.tz === null) errors.origin = COVERAGE_MESSAGE

  if (!destination) errors.destination = 'Choose a destination from the suggestions.'
  else if (destination.tz === null) errors.destination = COVERAGE_MESSAGE
  else if (origin && haversineMi(origin, destination) < MIN_TRIP_SEPARATION_MI) {
    errors.destination = 'Choose a destination different from the origin.'
  }

  if (origin?.tz) {
    const departure = input.departure ? parseLocal(input.departure, origin.tz) : null
    if (!input.departure) errors.departure = 'Choose a departure time.'
    else if (!departure) errors.departure = 'Departure must look like 2026-11-24T15:00.'
    else if (departure < now.minus({ minutes: DEPARTURE_PAST_GRACE_MIN })) {
      errors.departure = "Departure can't be in the past."
    } else if (departure > now.plus({ hours: DEPARTURE_MAX_AHEAD_H })) {
      errors.departure = `Departure must be within the next ${DEPARTURE_MAX_AHEAD_H} hours.`
    }
  } else if (!input.departure) {
    errors.departure = 'Choose a departure time.'
  }

  const load = input.load.trim() === '' ? NaN : Number(input.load)
  let warning: string | undefined
  if (Number.isNaN(load)) errors.load = 'Enter the cargo weight in pounds.'
  else if (load < LOAD_MIN_LB || load > LOAD_MAX_LB) {
    errors.load = `Load must be between ${formatLb(LOAD_MIN_LB)} and ${formatLb(LOAD_MAX_LB)} lb.`
  } else if (load > LOAD_WARNING_LB) warning = LOAD_WARNING_TEXT

  if (Object.keys(errors).length > 0 || !origin || !destination) return { errors, warning }
  return {
    errors,
    warning,
    request: {
      origin: { label: origin.label, lat: origin.lat, lon: origin.lon },
      destination: { label: destination.label, lat: destination.lat, lon: destination.lon },
      departure_local: input.departure,
      load_lb: load,
    },
  }
}
