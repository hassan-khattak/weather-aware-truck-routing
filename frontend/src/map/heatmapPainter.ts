import type { DecodedHeatmap, LayerName } from '../lib/heatmapDecode'
import { cellValue } from '../lib/heatmapDecode'
import { latFromMercatorY, lonFromMercatorX, mercatorX, mercatorY } from '../lib/mercator'
import { colorFor } from '../lib/ramps'

/** Pixels per heatmap cell, and the longest side of a bitmap (49 of them are kept in memory). */
const CELL_PX = 8
const MAX_SIDE_PX = 1024
const PADDING_CELLS = 1

export interface Geometry {
  width: number
  height: number
  /** Mercator-linear box of the canvas, in normalised world coordinates. */
  box: { x0: number; x1: number; y0: number; y1: number }
  /** Corners for a MapLibre canvas source: top-left, top-right, bottom-right, bottom-left. */
  coordinates: [[number, number], [number, number], [number, number], [number, number]]
}

/** The canvas covering the corridor, sized so each cell is a few pixels, linear in Mercator. */
export function canvasGeometry(d: DecodedHeatmap): Geometry {
  const half = d.gridDeg / 2
  const pad = PADDING_CELLS * d.gridDeg
  let west = Infinity
  let east = -Infinity
  let south = Infinity
  let north = -Infinity
  for (let i = 0; i < d.cellCount; i++) {
    const lat = d.cells[2 * i]
    const lon = d.cells[2 * i + 1]
    west = Math.min(west, lon - half)
    east = Math.max(east, lon + half)
    south = Math.min(south, lat - half)
    north = Math.max(north, lat + half)
  }
  west -= pad
  east += pad
  south -= pad
  north += pad
  const box = {
    x0: mercatorX(west),
    x1: mercatorX(east),
    y0: mercatorY(north),
    y1: mercatorY(south),
  }
  // Pixels per Mercator unit: CELL_PX per cell width, reduced to fit the longest side cap.
  const cellsAcross = (east - west) / d.gridDeg
  let scale = (cellsAcross * CELL_PX) / (box.x1 - box.x0)
  scale = Math.min(scale, MAX_SIDE_PX / Math.max(box.x1 - box.x0, box.y1 - box.y0))
  return {
    width: Math.max(1, Math.round((box.x1 - box.x0) * scale)),
    height: Math.max(1, Math.round((box.y1 - box.y0) * scale)),
    box,
    coordinates: [
      [west, north],
      [east, north],
      [east, south],
      [west, south],
    ],
  }
}

/** The part of a 2D canvas context the painter uses (so it can be faked in tests). */
export interface Context2D {
  fillStyle: string
  filter?: string
  globalAlpha: number
  fillRect(x: number, y: number, w: number, h: number): void
  clearRect(x: number, y: number, w: number, h: number): void
  drawImage(image: unknown, dx: number, dy: number): void
}

export interface Surface {
  ctx: Context2D
  source: CanvasImageSource
}

export type SurfaceFactory = (width: number, height: number) => Surface

export function defaultSurface(width: number, height: number): Surface {
  if (typeof OffscreenCanvas !== 'undefined') {
    const canvas = new OffscreenCanvas(width, height)
    return { ctx: canvas.getContext('2d') as unknown as Context2D, source: canvas }
  }
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  return { ctx: canvas.getContext('2d') as unknown as Context2D, source: canvas }
}

const rgba = ([r, g, b, a]: [number, number, number, number]) => `rgba(${r}, ${g}, ${b}, ${a})`

/**
 * Paint one hour of one layer: each cell is a rectangle placed by Web Mercator y (so long
 * north–south corridors do not drift), then the whole picture is softened with a blur.
 */
export function paintHour(
  d: DecodedHeatmap,
  layer: LayerName,
  hour: number,
  geometry: Geometry,
  makeSurface: SurfaceFactory = defaultSurface,
): Surface {
  const { width, height, box } = geometry
  const cells = makeSurface(width, height)
  const half = d.gridDeg / 2
  const spanX = box.x1 - box.x0
  const spanY = box.y1 - box.y0
  for (let i = 0; i < d.cellCount; i++) {
    const color = colorFor(layer, cellValue(d, layer, hour, i))
    if (!color) continue
    const lat = d.cells[2 * i]
    const lon = d.cells[2 * i + 1]
    const left = ((mercatorX(lon - half) - box.x0) / spanX) * width
    const right = ((mercatorX(lon + half) - box.x0) / spanX) * width
    const top = ((mercatorY(lat + half) - box.y0) / spanY) * height
    const bottom = ((mercatorY(lat - half) - box.y0) / spanY) * height
    cells.ctx.fillStyle = rgba(color)
    // A little overlap hides hairline seams between neighbouring cells.
    cells.ctx.fillRect(left - 0.5, top - 0.5, right - left + 1, bottom - top + 1)
  }
  const out = makeSurface(width, height)
  out.ctx.filter = `blur(${CELL_PX * 0.6}px)` // not supported everywhere; then cells stay crisp
  out.ctx.drawImage(cells.source, 0, 0)
  return out
}

/** Latitude of a canvas row, for tests and hover maths. */
export function latAtRow(geometry: Geometry, row: number): number {
  const { box, height } = geometry
  return latFromMercatorY(box.y0 + (row / height) * (box.y1 - box.y0))
}

export function lonAtColumn(geometry: Geometry, column: number): number {
  const { box, width } = geometry
  return lonFromMercatorX(box.x0 + (column / width) * (box.x1 - box.x0))
}
