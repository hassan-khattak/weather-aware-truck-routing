import type { LayerName } from '../lib/heatmapDecode'
import type { HeatmapBitmaps } from './heatmapBitmaps'

export const HEATMAP_SOURCE = 'heatmap'
export const HEATMAP_LAYER = 'heatmap'

type Corners = [[number, number], [number, number], [number, number], [number, number]]

interface CanvasSourceLike {
  setCoordinates(coordinates: Corners): unknown
  play(): void
  pause(): void
}

/** The part of MapLibre's Map the heatmap layer uses (so it can be faked in tests). */
export interface HeatmapMap {
  addSource(id: string, source: unknown): unknown
  addLayer(layer: unknown, beforeId?: string): unknown
  getSource(id: string): CanvasSourceLike | undefined
  setLayoutProperty(layer: string, name: string, value: unknown): unknown
  triggerRepaint(): void
  once(type: 'render', listener: () => void): unknown
}

interface CanvasLike {
  width: number
  height: number
  getContext(type: '2d'): CanvasContext | null
}

interface CanvasContext {
  globalAlpha: number
  clearRect(x: number, y: number, w: number, h: number): void
  drawImage(image: CanvasImageSource, x: number, y: number): void
}

const PLACEHOLDER: Corners = [
  [-1, 1],
  [1, 1],
  [1, -1],
  [-1, -1],
]

/**
 * The weather glow: one canvas source and one raster layer, created once. Showing an hour copies
 * a precomputed picture onto the canvas (two of them, cross-faded, between hours); MapLibre
 * only re-reads the canvas for the frame after a change.
 */
export class HeatmapLayer {
  private readonly map: HeatmapMap
  private readonly canvas: CanvasLike
  private ctx: CanvasContext | null = null
  private bitmaps: HeatmapBitmaps | null = null
  private layer: LayerName = 'risk'
  private visible = true
  private hour = 0
  private created = false
  private pushPending = false
  private holdOpen = false

  constructor(
    map: HeatmapMap,
    createCanvas: () => CanvasLike = () => document.createElement('canvas'),
  ) {
    this.map = map
    this.canvas = createCanvas()
  }

  /** Call once the style has loaded, BEFORE the route and checkpoint layers, so it sits below. */
  ready(beforeId?: string): void {
    if (this.created) return
    this.created = true
    this.canvas.width = 1
    this.canvas.height = 1
    this.ctx = this.canvas.getContext('2d')
    this.map.addSource(HEATMAP_SOURCE, {
      type: 'canvas',
      canvas: this.canvas,
      coordinates: PLACEHOLDER,
      animate: false, // copied only for frames that follow a change (see push)
    })
    this.map.addLayer(
      {
        id: HEATMAP_LAYER,
        type: 'raster',
        source: HEATMAP_SOURCE,
        layout: { visibility: this.visible ? 'visible' : 'none' },
        paint: { 'raster-fade-duration': 0, 'raster-resampling': 'linear' },
      },
      beforeId,
    )
    this.fit()
    this.draw()
  }

  /** New weather for a new search (or none). Resizes the canvas and moves it to the corridor. */
  setBitmaps(bitmaps: HeatmapBitmaps | null): void {
    this.bitmaps = bitmaps
    this.fit()
    this.draw()
  }

  /** Size the canvas to the corridor and place it on the map (or shrink it away). */
  private fit(): void {
    if (!this.created) return
    const { bitmaps } = this
    this.canvas.width = bitmaps ? bitmaps.geometry.width : 1
    this.canvas.height = bitmaps ? bitmaps.geometry.height : 1
    if (bitmaps) this.map.getSource(HEATMAP_SOURCE)?.setCoordinates(bitmaps.geometry.coordinates)
  }

  setLayer(layer: LayerName): void {
    this.layer = layer
    this.bitmaps?.precompute(layer)
    this.draw()
  }

  setVisible(visible: boolean): void {
    this.visible = visible
    if (this.created) {
      this.map.setLayoutProperty(HEATMAP_LAYER, 'visibility', visible ? 'visible' : 'none')
    }
    this.draw()
  }

  /** Show the weather at `hour` after departure; fractions cross-fade two neighbouring hours. */
  show(hour: number): void {
    this.hour = hour
    this.draw()
  }

  /** While playing, keep MapLibre copying the canvas every frame instead of once per change. */
  setPlaying(playing: boolean): void {
    this.holdOpen = playing
    if (!playing) this.map.getSource(HEATMAP_SOURCE)?.pause()
    else this.map.getSource(HEATMAP_SOURCE)?.play()
  }

  private draw(): void {
    if (!this.created || !this.ctx) return
    const { ctx, canvas, bitmaps } = this
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!bitmaps || !this.visible) return this.push()
    const last = bitmaps.maxHour
    const clamped = Math.min(Math.max(this.hour, 0), last)
    const lower = Math.floor(clamped)
    const upper = Math.min(lower + 1, last)
    const fraction = clamped - lower
    ctx.globalAlpha = fraction === 0 || upper === lower ? 1 : 1 - fraction
    ctx.drawImage(bitmaps.get(this.layer, lower), 0, 0)
    if (fraction > 0 && upper !== lower) {
      ctx.globalAlpha = fraction
      ctx.drawImage(bitmaps.get(this.layer, upper), 0, 0)
    }
    ctx.globalAlpha = 1
    this.push()
  }

  /** Make MapLibre copy the canvas on the next frame, then stop copying (unless playing). */
  private push(): void {
    const source = this.map.getSource(HEATMAP_SOURCE)
    if (!source) return
    source.play()
    this.map.triggerRepaint()
    if (this.holdOpen || this.pushPending) return
    this.pushPending = true
    this.map.once('render', () => {
      this.pushPending = false
      if (!this.holdOpen) source.pause()
    })
  }
}
