import type { Place } from '../api/types'

export interface SampleTrip {
  slug: string
  title: string
  detail: string
  origin: Place
  destination: Place
}

const place = (label: string, lat: number, lon: number, tz: string): Place => ({
  label,
  lat,
  lon,
  tz,
})

/** One-click demo trips (plan.md section 3.13); same places the backend fixtures are recorded for. */
export const SAMPLE_TRIPS: SampleTrip[] = [
  {
    slug: 'denver-cheyenne',
    title: 'Denver → Cheyenne',
    detail: 'Short trip, 10 mi checkpoints',
    origin: place('Denver, CO', 39.7392, -104.9903, 'America/Denver'),
    destination: place('Cheyenne, WY', 41.14, -104.8202, 'America/Denver'),
  },
  {
    slug: 'saltlake-denver',
    title: 'Salt Lake City → Denver',
    detail: 'High-wind corridor, 25 mi checkpoints',
    origin: place('Salt Lake City, UT', 40.7608, -111.891, 'America/Denver'),
    destination: place('Denver, CO', 39.7392, -104.9903, 'America/Denver'),
  },
  {
    slug: 'chicago-dallas',
    title: 'Chicago → Dallas',
    detail: 'Overnight rest stop',
    origin: place('Chicago, IL', 41.8781, -87.6298, 'America/Chicago'),
    destination: place('Dallas, TX', 32.7767, -96.797, 'America/Chicago'),
  },
  {
    slug: 'seattle-chicago',
    title: 'Seattle → Chicago',
    detail: 'Multi-day trip, several rests',
    origin: place('Seattle, WA', 47.6062, -122.3321, 'America/Los_Angeles'),
    destination: place('Chicago, IL', 41.8781, -87.6298, 'America/Chicago'),
  },
]
