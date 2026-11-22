export const DEFAULT_MAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty'

/** Continental US, as [[west, south], [east, north]]. */
export const US_BOUNDS: [[number, number], [number, number]] = [
  [-125, 24],
  [-66.5, 49.5],
]

export interface AppConfig {
  mapStyleUrl: string
}

/** Runtime config from Vite env vars. The basemap needs no API key. */
export function readConfig(env: { VITE_MAP_STYLE_URL?: string }): AppConfig {
  return { mapStyleUrl: env.VITE_MAP_STYLE_URL?.trim() || DEFAULT_MAP_STYLE_URL }
}

export const config = readConfig(import.meta.env)
