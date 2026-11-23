/** Web Mercator, normalised to the unit square: x 0 (180°W) to 1 (180°E), y 0 (north) to 1. */
export const mercatorX = (lon: number) => (lon + 180) / 360

export function mercatorY(lat: number): number {
  const rad = (lat * Math.PI) / 180
  return (1 - Math.log(Math.tan(Math.PI / 4 + rad / 2)) / Math.PI) / 2
}

export function latFromMercatorY(y: number): number {
  return (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI
}

export const lonFromMercatorX = (x: number) => x * 360 - 180
