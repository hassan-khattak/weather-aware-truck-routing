import { DateTime } from 'luxon'
import type { Checkpoint } from '../api/types'
import { LEVELS, type Level } from '../levels'
import { haversineMi } from './geo'

/** A town this close is "near"; farther away the distance and direction are shown. */
const NEAR_TOWN_MI = 5
/** Checkpoints of two routes closer than this are the same stretch of road. */
const SHARED_ROAD_MI = 1

const LEVEL_EMOJI: Record<Level, string> = {
  LOW: '🟢',
  MODERATE: '🟡',
  HIGH: '🟠',
  SEVERE: '🔴',
  NO_TRAVEL: '🟣',
  NO_FORECAST: '⚪',
}

export const SHARED_ROAD_NOTE =
  'Risk differs from other routes here because the truck arrives at a different time.'

/** "I-40 W near Amarillo, TX", or "I-40 W · 28 mi W of Tucumcari, NM" when the town is far. */
export function placeText(cp: Checkpoint): string {
  const road = cp.road ?? ''
  if (!cp.town) return road
  const far = cp.town_dist_mi !== null && cp.town_dist_mi > NEAR_TOWN_MI
  const town =
    far && cp.town_dir ? `${Math.round(cp.town_dist_mi!)} mi ${cp.town_dir} of ${cp.town}` : null
  if (town) return road ? `${road} · ${town}` : town
  return road ? `${road} near ${cp.town}` : `near ${cp.town}`
}

/** "ETA Tue 8:40 PM CST", in the checkpoint's own time zone. */
export function etaText(cp: Checkpoint): string {
  const at = DateTime.fromISO(cp.eta_utc, { zone: 'utc' }).setZone(cp.tz)
  return `ETA ${at.toFormat('ccc h:mm a')} ${at.offsetNameShort}`
}

const trimmed = (value: number) => String(Number(value.toFixed(2)))

export function weatherText(cp: Checkpoint): string {
  if (cp.wind_mph === null || cp.gust_mph === null) return 'No forecast available'
  const parts = [`Wind ${Math.round(cp.wind_mph)} mph (gusts ${Math.round(cp.gust_mph)})`]
  if (cp.rain_in_hr !== null) parts.push(`Rain ${trimmed(cp.rain_in_hr)} in/hr`)
  if (cp.snow_in_hr !== null) parts.push(`Snow ${trimmed(cp.snow_in_hr)} in/hr`)
  return parts.join(' · ')
}

/** The level in words (never colour alone), with the reasons behind it. */
export function reasonText(cp: Checkpoint): string {
  const head = `${LEVEL_EMOJI[cp.level]} ${LEVELS[cp.level].label.toUpperCase()}`
  if (cp.reasons.length > 0) return `${head}: ${cp.reasons.join('; ')}`
  return cp.level === 'LOW' ? `${head}: Within limits` : head
}

export function tooltipLines(cp: Checkpoint): string[] {
  const place = placeText(cp)
  const title = `CP ${cp.idx + 1} · Mile ${Math.round(cp.mile)}${place ? ` · ${place}` : ''}`
  return [title, etaText(cp), weatherText(cp), reasonText(cp)]
}

/** Trap T8: the same road can have a different level on another route (different arrival time). */
export function sharedRoadNote(cp: Checkpoint, otherRoutes: Checkpoint[][]): string | null {
  const differs = otherRoutes.some((points) =>
    points.some((p) => p.level !== cp.level && haversineMi(cp, p) <= SHARED_ROAD_MI),
  )
  return differs ? SHARED_ROAD_NOTE : null
}
