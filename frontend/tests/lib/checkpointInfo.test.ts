import { describe, expect, it } from 'vitest'
import type { Checkpoint } from '../../src/api/types'
import {
  etaText,
  placeText,
  reasonText,
  sharedRoadNote,
  tooltipLines,
  weatherText,
} from '../../src/lib/checkpointInfo'

function cp(over: Partial<Checkpoint> = {}): Checkpoint {
  return {
    idx: 6,
    mile: 175,
    lat: 35.2,
    lon: -101.8,
    eta_utc: '2026-11-25T02:40:00Z',
    tz: 'America/Chicago',
    road: 'I-40 W',
    town: 'Amarillo, TX',
    town_dist_mi: 2.1,
    town_dir: 'N',
    wind_mph: 38.2,
    gust_mph: 51.4,
    rain_in_hr: 0.05,
    snow_in_hr: 0,
    level: 'SEVERE',
    reasons: ['Wind 38 mph → High', 'Load 42,000 lb > 40,000 → Severe'],
    forecast: true,
    ...over,
  }
}

describe('placeText', () => {
  it('says "near" when the town is close', () => {
    expect(placeText(cp())).toBe('I-40 W near Amarillo, TX')
  })
  it('gives distance and direction when the town is far', () => {
    expect(placeText(cp({ town: 'Tucumcari, NM', town_dist_mi: 28.4, town_dir: 'W' }))).toBe(
      'I-40 W · 28 mi W of Tucumcari, NM',
    )
  })
  it('falls back gracefully', () => {
    expect(placeText(cp({ road: null }))).toBe('near Amarillo, TX')
    expect(placeText(cp({ town: null, town_dist_mi: null, town_dir: null }))).toBe('I-40 W')
    expect(placeText(cp({ road: null, town: null, town_dist_mi: null, town_dir: null }))).toBe('')
  })
})

describe('etaText', () => {
  it('uses the checkpoint zone', () => {
    expect(etaText(cp())).toBe('ETA Tue 8:40 PM CST')
  })
  it('follows daylight time', () => {
    expect(etaText(cp({ eta_utc: '2026-07-07T02:40:00Z' }))).toBe('ETA Mon 9:40 PM CDT')
  })
})

describe('weatherText', () => {
  it('rounds wind and keeps two decimals for precipitation', () => {
    expect(weatherText(cp())).toBe('Wind 38 mph (gusts 51) · Rain 0.05 in/hr · Snow 0 in/hr')
  })
  it('says so when there is no forecast', () => {
    expect(
      weatherText(
        cp({ wind_mph: null, gust_mph: null, rain_in_hr: null, snow_in_hr: null, forecast: false }),
      ),
    ).toBe('No forecast available')
  })
})

describe('reasonText', () => {
  it('shows the level in words with its reasons', () => {
    expect(reasonText(cp())).toBe('🔴 SEVERE: Wind 38 mph → High; Load 42,000 lb > 40,000 → Severe')
  })
  it('handles levels without reasons', () => {
    expect(reasonText(cp({ level: 'LOW', reasons: [] }))).toBe('🟢 LOW: Within limits')
    expect(reasonText(cp({ level: 'NO_FORECAST', reasons: [] }))).toBe('⚪ NO FORECAST')
  })
})

describe('tooltipLines', () => {
  it('follows the plan format', () => {
    expect(tooltipLines(cp())).toEqual([
      'CP 7 · Mile 175 · I-40 W near Amarillo, TX',
      'ETA Tue 8:40 PM CST',
      'Wind 38 mph (gusts 51) · Rain 0.05 in/hr · Snow 0 in/hr',
      '🔴 SEVERE: Wind 38 mph → High; Load 42,000 lb > 40,000 → Severe',
    ])
  })
  it('omits the place when nothing is known', () => {
    const lines = tooltipLines(cp({ road: null, town: null, town_dist_mi: null, town_dir: null }))
    expect(lines[0]).toBe('CP 7 · Mile 175')
  })
})

describe('sharedRoadNote', () => {
  const other = (over: Partial<Checkpoint>) => cp({ idx: 3, ...over })
  it('appears when another route is at the same spot with a different level', () => {
    const note = sharedRoadNote(cp(), [[other({ level: 'LOW', lat: 35.2005 })]])
    expect(note).toBe(
      'Risk differs from other routes here because the truck arrives at a different time.',
    )
  })
  it('is absent when levels match, the spot is far, or there is no other route', () => {
    expect(sharedRoadNote(cp(), [[other({ lat: 35.2005 })]])).toBeNull()
    expect(sharedRoadNote(cp(), [[other({ level: 'LOW', lat: 36.5 })]])).toBeNull()
    expect(sharedRoadNote(cp(), [])).toBeNull()
  })
})
