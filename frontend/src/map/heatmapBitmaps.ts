import type { DecodedHeatmap, LayerName } from '../lib/heatmapDecode'
import {
  canvasGeometry,
  defaultSurface,
  paintHour,
  type Geometry,
  type SurfaceFactory,
} from './heatmapPainter'

export type Scheduler = (task: () => void) => void

/** Runs `task` when the browser is idle (or soon, where it has no idle callback). */
export const idleScheduler: Scheduler = (task) => {
  if (typeof requestIdleCallback === 'function') requestIdleCallback(() => task())
  else setTimeout(task, 0)
}

/** Keeps the bitmaps of this many layers (current and previous), so switching back is instant. */
const KEPT_LAYERS = 2

type Image = CanvasImageSource

/**
 * The picture of every forecast hour for a layer. One hour is painted on demand (so the slider
 * never waits); all hours are then converted to ImageBitmaps one per idle slot, off the
 * interaction path. Nothing here runs while the user drags: drawing an hour is a cache lookup.
 */
export class HeatmapBitmaps {
  readonly geometry: Geometry
  /** The last forecast hour (hours are numbered from 0). */
  readonly maxHour: number
  private readonly data: DecodedHeatmap
  private readonly schedule: Scheduler
  private readonly makeSurface: SurfaceFactory
  private readonly toBitmap: (source: Image) => Promise<Image>
  private readonly cache = new Map<LayerName, Map<number, Image>>()
  private readonly recent: LayerName[] = []
  private generation = 0

  constructor(
    data: DecodedHeatmap,
    options: {
      schedule?: Scheduler
      makeSurface?: SurfaceFactory
      toBitmap?: (source: Image) => Promise<Image>
    } = {},
  ) {
    this.data = data
    this.geometry = canvasGeometry(data)
    this.maxHour = data.hours - 1
    this.schedule = options.schedule ?? idleScheduler
    this.makeSurface = options.makeSurface ?? defaultSurface
    this.toBitmap = options.toBitmap ?? ((source) => createImageBitmap(source as ImageBitmapSource))
  }

  /** The picture for an hour, painting it right now if it is not ready yet. */
  get(layer: LayerName, hour: number): Image {
    const hours = this.hoursOf(layer)
    const hit = hours.get(hour)
    if (hit) return hit
    const image = paintHour(this.data, layer, hour, this.geometry, this.makeSurface).source
    hours.set(hour, image)
    return image
  }

  /** Start converting every hour of a layer to a bitmap, one per idle slot. */
  precompute(layer: LayerName): void {
    const generation = ++this.generation
    this.touch(layer)
    const queue = Array.from({ length: this.data.hours }, (_, hour) => hour)
    const step = () => {
      if (generation !== this.generation) return // a newer layer took over
      const hour = queue.shift()
      if (hour === undefined) return
      const hours = this.hoursOf(layer)
      const image = hours.get(hour) ?? this.get(layer, hour)
      void this.toBitmap(image).then((bitmap) => {
        if (this.cache.get(layer) === hours) hours.set(hour, bitmap)
      })
      this.schedule(step)
    }
    this.schedule(step)
  }

  /** Whether every hour of the layer has been painted (used by tests and the loading hint). */
  has(layer: LayerName, hour: number): boolean {
    return this.cache.get(layer)?.has(hour) ?? false
  }

  dispose(): void {
    this.generation++
    for (const hours of this.cache.values()) {
      for (const image of hours.values()) (image as ImageBitmap).close?.()
    }
    this.cache.clear()
    this.recent.length = 0
  }

  private hoursOf(layer: LayerName): Map<number, Image> {
    let hours = this.cache.get(layer)
    if (!hours) {
      hours = new Map()
      this.cache.set(layer, hours)
    }
    this.touch(layer)
    return hours
  }

  private touch(layer: LayerName): void {
    const at = this.recent.indexOf(layer)
    if (at >= 0) this.recent.splice(at, 1)
    this.recent.unshift(layer)
    while (this.recent.length > KEPT_LAYERS) {
      const dropped = this.recent.pop()!
      for (const image of this.cache.get(dropped)?.values() ?? []) (image as ImageBitmap).close?.()
      this.cache.delete(dropped)
    }
  }
}
