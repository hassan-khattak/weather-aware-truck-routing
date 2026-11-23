import { DateTime } from 'luxon'
import { DEPARTURE_MAX_AHEAD_H, DEPARTURE_PAST_GRACE_MIN } from './limits'

/** The wall-clock format the API expects and a datetime-local input uses. */
export const LOCAL_FORMAT = "yyyy-MM-dd'T'HH:mm"

export type Clock = () => DateTime

/** Next full hour in the origin's zone, as a wall-clock string (the default departure). */
export function nextFullHour(zone: string, now: DateTime): string {
  return now.setZone(zone).startOf('hour').plus({ hours: 1 }).toFormat(LOCAL_FORMAT)
}

/** "CST · Chicago": the zone abbreviation and city at that moment (CST/CDT follows daylight time). */
export function zoneLabel(zone: string, at: DateTime): string {
  const city = zone.split('/').pop()!.replace(/_/g, ' ')
  return `${at.setZone(zone).offsetNameShort} · ${city}`
}

/** Earliest and latest departure the form accepts, as wall-clock strings in `zone`. */
export function departureWindow(zone: string, now: DateTime): { min: string; max: string } {
  const local = now.setZone(zone)
  return {
    min: local.minus({ minutes: DEPARTURE_PAST_GRACE_MIN }).toFormat(LOCAL_FORMAT),
    max: local.plus({ hours: DEPARTURE_MAX_AHEAD_H }).toFormat(LOCAL_FORMAT),
  }
}

/** Parse a wall-clock string in `zone`; null if it is not a valid time. */
export function parseLocal(text: string, zone: string): DateTime | null {
  const parsed = DateTime.fromFormat(text, LOCAL_FORMAT, { zone })
  return parsed.isValid ? parsed : null
}

/** "Tue 3 PM CST", for the one-line summary of a search. */
export function summaryTime(local: string, zone: string): string {
  const parsed = parseLocal(local, zone)
  if (!parsed) return local
  const time = parsed.minute === 0 ? parsed.toFormat('h a') : parsed.toFormat('h:mm a')
  return `${parsed.toFormat('ccc')} ${time} ${parsed.offsetNameShort}`
}
