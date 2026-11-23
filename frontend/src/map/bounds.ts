export type LngLat = [number, number]
export type Bounds = [LngLat, LngLat] // [[west, south], [east, north]]

/** The box around all coordinates; null if there are none. */
export function boundsOf(lines: LngLat[][]): Bounds | null {
  let west = Infinity
  let south = Infinity
  let east = -Infinity
  let north = -Infinity
  for (const line of lines) {
    for (const [lng, lat] of line) {
      west = Math.min(west, lng)
      east = Math.max(east, lng)
      south = Math.min(south, lat)
      north = Math.max(north, lat)
    }
  }
  return Number.isFinite(west)
    ? [
        [west, south],
        [east, north],
      ]
    : null
}
