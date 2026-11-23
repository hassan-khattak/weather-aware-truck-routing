import type { Route } from '../api/types'
import { EMPTY_FEATURES } from './features'
import { cumulativeMiles } from './features'
import type { MapLike } from './routeLayers'
import { toLngLat } from './routeLayers'
import { truckAt } from './truck'

export const TRUCK_SOURCE = 'truck'
export const TRUCK_LAYER = 'truck'

type Frame = (callback: () => void) => unknown

/**
 * The truck marker: a single point whose position follows the selected route's timeline. Updates
 * are coalesced to one per animation frame, so a fast drag or Play costs one small setData per
 * frame. Distances along the route are computed once per route, not per frame.
 */
export class TruckLayer {
  private readonly map: Pick<MapLike, 'addSource' | 'addLayer' | 'getSource'>
  private readonly frame: Frame
  private created = false
  private route: Route | undefined
  private line: [number, number][] = []
  private lengths: number[] = []
  private windowS = Infinity
  private hour = 0
  private framePending = false

  constructor(
    map: Pick<MapLike, 'addSource' | 'addLayer' | 'getSource'>,
    frame: Frame = (cb) => requestAnimationFrame(cb),
  ) {
    this.map = map
    this.frame = frame
  }

  ready(): void {
    if (this.created) return
    this.created = true
    this.map.addSource(TRUCK_SOURCE, { type: 'geojson', data: EMPTY_FEATURES })
    this.map.addLayer({
      id: TRUCK_LAYER,
      type: 'circle',
      source: TRUCK_SOURCE,
      paint: {
        'circle-radius': 9,
        'circle-color': '#111827',
        'circle-stroke-width': 3,
        'circle-stroke-color': '#ffffff',
      },
    })
    this.render()
  }

  /** The route the truck drives (none before there is weather), and how many hours the forecast covers. */
  setRoute(route: Route | undefined, windowHours: number): void {
    if (route !== this.route) {
      this.route = route
      this.line = route ? toLngLat(route.geometry) : []
      this.lengths = cumulativeMiles(this.line)
    }
    this.windowS = windowHours * 3600
    this.schedule()
  }

  /** Where the truck is `hour` hours after departure (fractions while playing). */
  show(hour: number): void {
    this.hour = hour
    this.schedule()
  }

  private schedule(): void {
    if (!this.created || this.framePending) return
    this.framePending = true
    this.frame(() => {
      this.framePending = false
      this.render()
    })
  }

  private render(): void {
    const source = this.map.getSource(TRUCK_SOURCE)
    if (!source) return
    if (!this.route) return source.setData(EMPTY_FEATURES)
    const truck = truckAt(this.route, this.line, this.hour * 3600, this.windowS, this.lengths)
    source.setData({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { state: truck.state },
          geometry: { type: 'Point', coordinates: truck.position },
        },
      ],
    })
  }
}
