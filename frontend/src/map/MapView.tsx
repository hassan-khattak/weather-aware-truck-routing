import { Map, NavigationControl, Popup } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import type { RiskResponse, Route, RoutesResponse } from '../api/types'
import { config, US_BOUNDS } from '../config'
import type { Checkpoint } from '../api/types'
import { sharedRoadNote } from '../lib/checkpointInfo'
import { CheckpointLayers, HIGHLIGHT_LAYER } from './checkpointLayers'
import { decodeHeatmap } from '../lib/heatmapDecode'
import { layerId, ROUTE_IDS } from './routeLayers'
import { useUiStore } from '../state/uiStore'
import { cellAt, type DecodedHeatmap } from '../lib/heatmapDecode'
import { heatmapHoverLines } from '../lib/heatmapHover'
import { TruckLayer } from './truckLayer'
import { DOT_LAYER } from './checkpointLayers'
import { HeatmapBitmaps } from './heatmapBitmaps'
import { HeatmapLayer, type HeatmapMap } from './heatmapLayer'
import { RouteLayers, type Hover, type MapLike } from './routeLayers'
import { checkpointTooltip, type CheckpointTooltip } from './tooltip'

interface Props {
  routes?: RoutesResponse
  risk?: RiskResponse
  selectedId: string | null
  onSelect: (routeId: string) => void
  /** The checkpoint pinned by a click (tooltip stays open), or null. */
  activeCheckpoint: number | null
  onPickCheckpoint: (idx: number | null) => void
}

const NO_ROUTES: Route[] = []
const SMALL_SCREEN_PX = 768

/** Room around the fitted routes: on small screens the bottom sheet covers part of the map. */
function fitPadding() {
  const small = window.innerWidth < SMALL_SCREEN_PX
  return {
    top: 40,
    left: 40,
    right: 40,
    bottom: small ? Math.round(window.innerHeight * 0.55) : 40,
  }
}

/** Fitting the map to new routes animates, unless the person asked for less motion. */
function fitDuration() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 0 : 600
}

function popupHover(map: Map): Hover {
  const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 12 })
  return {
    show(_routeId, at, lines) {
      const content = document.createElement('div')
      content.className = 'text-xs'
      lines.forEach((text, index) => {
        const row = document.createElement('div')
        row.textContent = text // textContent, never HTML: place and road names are data
        if (index === 0) row.className = 'font-semibold'
        content.append(row)
      })
      popup.setLngLat([at.lng, at.lat]).setDOMContent(content).addTo(map)
    },
    hide() {
      popup.remove()
    },
  }
}

export function MapView({
  routes,
  risk,
  selectedId,
  onSelect,
  activeCheckpoint,
  onPickCheckpoint,
}: Props) {
  const container = useRef<HTMLDivElement>(null)
  const layers = useRef<RouteLayers | null>(null)
  const mapRef = useRef<Map | null>(null)
  const heat = useRef<HeatmapLayer | null>(null)
  const truck = useRef<TruckLayer | null>(null)
  const decoded = useRef<{ data: DecodedHeatmap; tz: string } | null>(null)
  const checkpoints = useRef<CheckpointLayers | null>(null)
  const tooltip = useRef<CheckpointTooltip | null>(null)
  const latestOnSelect = useRef(onSelect)
  const latestOnPick = useRef(onPickCheckpoint)
  // What the map handlers need to know about the current route's checkpoints.
  const shown = useRef<{ points: Checkpoint[]; others: Checkpoint[][]; active: number | null }>({
    points: [],
    others: [],
    active: null,
  })

  useEffect(() => {
    latestOnSelect.current = onSelect
    latestOnPick.current = onPickCheckpoint
  }, [onSelect, onPickCheckpoint])

  // The map and its route layers are created once.
  useEffect(() => {
    if (!container.current) return
    const map = new Map({
      container: container.current,
      style: config.mapStyleUrl,
      bounds: US_BOUNDS,
      fitBoundsOptions: { padding: 20 },
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    mapRef.current = map
    const heatmap = new HeatmapLayer(map as unknown as HeatmapMap)
    heat.current = heatmap
    const truckLayer = new TruckLayer(map as unknown as MapLike)
    truck.current = truckLayer
    const valuePopup = popupHover(map)
    // Hovering the glow (not a route or a dot) shows the weather values of the cell below.
    map.on('mousemove', (event) => {
      const data = decoded.current
      const state = useUiStore.getState()
      const onFeature = map.queryRenderedFeatures(event.point, {
        layers: [DOT_LAYER, ...ROUTE_IDS.map(layerId)].filter((id) => map.getLayer(id)),
      })
      const cell =
        data && state.heatmapVisible && !onFeature.length
          ? cellAt(data.data, event.lngLat.lng, event.lngLat.lat)
          : null
      if (cell === null || !data) return valuePopup.hide()
      const hour = Math.min(Math.max(Math.round(state.hour), 0), data.data.hours - 1)
      valuePopup.show('heatmap', event.lngLat, heatmapHoverLines(data.data, hour, cell, data.tz))
    })
    map.getCanvas().addEventListener('mouseleave', () => valuePopup.hide())
    const tip = checkpointTooltip(map)
    tooltip.current = tip
    const showCheckpoint = (idx: number | null) => {
      const cp = idx === null ? undefined : shown.current.points.find((p) => p.idx === idx)
      if (cp) tip.show(cp, sharedRoadNote(cp, shown.current.others))
      else tip.hide()
    }
    // Created before the route lines so the lines can be inserted below the dots.
    // A dot sits on its route line; over a dot only the checkpoint tooltip shows.
    const routePopup = popupHover(map)
    let overDot = false
    const routeHover: Hover = {
      show: (...args) => {
        if (!overDot) routePopup.show(...args)
      },
      hide: () => routePopup.hide(),
    }
    const checkpointLayers = new CheckpointLayers(map as unknown as MapLike, {
      // Hovering previews a checkpoint; leaving returns to the pinned one, if any.
      onHover: (idx) => {
        overDot = idx !== null
        if (overDot) routePopup.hide()
        showCheckpoint(idx ?? shown.current.active)
      },
      onPick: (idx) => latestOnPick.current(idx),
    })
    checkpoints.current = checkpointLayers
    const routeLayers = new RouteLayers(
      map as unknown as MapLike,
      (id) => latestOnSelect.current(id),
      routeHover,
      fitPadding,
      fitDuration,
      HIGHLIGHT_LAYER,
    )
    layers.current = routeLayers
    // Lets the browser tests inspect the map; absent from production builds.
    if (import.meta.env.DEV) (window as unknown as { __truckMap?: unknown }).__truckMap = map
    map.on('load', () => {
      heatmap.ready() // first, so it sits below everything added after it
      checkpointLayers.ready()
      routeLayers.ready()
      truckLayer.ready() // last: the truck is drawn above everything
    })
    return () => {
      layers.current = null
      checkpoints.current = null
      heat.current = null
      truck.current = null
      decoded.current = null
      mapRef.current = null
      tooltip.current = null
      map.remove()
    }
  }, [])

  // Data and selection only update what is already there.
  const routeList = routes?.routes ?? NO_ROUTES
  const riskList = risk?.routes
  useEffect(() => {
    layers.current?.update({ routes: routeList, risk: riskList, selectedId })
  }, [routeList, riskList, selectedId])

  const tz = routes?.departure.tz ?? 'America/Chicago'

  // The weather glow: decoded once per response, painted once, then only re-drawn per hour.
  const heatmapData = risk?.heatmap
  useEffect(() => {
    const layer = heat.current
    if (!layer || !heatmapData) return
    const data = decodeHeatmap(heatmapData)
    if (data.cellCount === 0) return // nothing to draw (no weather corridor)
    const bitmaps = new HeatmapBitmaps(data)
    decoded.current = { data, tz }
    const state = useUiStore.getState()
    layer.setBitmaps(bitmaps)
    layer.setLayer(state.heatmapLayer)
    layer.setVisible(state.heatmapVisible)
    layer.show(state.hour)
    truck.current?.show(state.hour)
    // Time, layer and visibility changes go straight to the map; React does not re-render.
    const unsubscribe = useUiStore.subscribe((now, before) => {
      if (now.heatmapLayer !== before.heatmapLayer) layer.setLayer(now.heatmapLayer)
      if (now.playing !== before.playing) layer.setPlaying(now.playing)
      if (now.heatmapVisible !== before.heatmapVisible) layer.setVisible(now.heatmapVisible)
      if (now.hour !== before.hour) {
        layer.show(now.hour)
        truck.current?.show(now.hour)
      }
    })
    return () => {
      unsubscribe()
      decoded.current = null
      layer.setBitmaps(null)
      bitmaps.dispose()
    }
  }, [heatmapData, tz])

  // Checkpoints belong to the selected route only.
  const selectedRoute = routeList.find((r) => r.id === selectedId)
  useEffect(() => {
    // The truck appears once there is weather (the forecast window is its time limit).
    truck.current?.setRoute(heatmapData ? selectedRoute : undefined, (heatmapData?.hours ?? 1) - 1)
  }, [selectedRoute, heatmapData])
  const selectedRisk = riskList?.find((r) => r.id === selectedId)
  useEffect(() => {
    checkpoints.current?.update({
      route: selectedRoute,
      risk: selectedRisk,
      activeIdx: activeCheckpoint,
    })
    shown.current = {
      points: selectedRisk?.checkpoints ?? [],
      others: (riskList ?? []).filter((r) => r.id !== selectedId).map((r) => r.checkpoints),
      active: activeCheckpoint,
    }
    // A pinned checkpoint keeps its tooltip open; Escape or picking elsewhere changes it.
    const cp = shown.current.points.find((p) => p.idx === activeCheckpoint)
    if (cp) tooltip.current?.show(cp, sharedRoadNote(cp, shown.current.others))
    else tooltip.current?.hide()
    // A pinned checkpoint that is off screen (a list pick) is brought into view.
    const map = mapRef.current
    if (cp && map && !map.getBounds().contains([cp.lon, cp.lat])) {
      map.easeTo({ center: [cp.lon, cp.lat], duration: fitDuration() })
    }
  }, [selectedRoute, selectedRisk, riskList, selectedId, activeCheckpoint])

  // Escape unpins the tooltip.
  useEffect(() => {
    if (activeCheckpoint === null) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') latestOnPick.current(null)
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [activeCheckpoint])

  return (
    <div
      ref={container}
      className="map"
      data-testid="map"
      role="region"
      aria-label="Map of the routes. Use the trip planner for route details."
    />
  )
}
