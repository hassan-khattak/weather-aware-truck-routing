import { Map, NavigationControl, Popup } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import type { RiskResponse, Route, RoutesResponse } from '../api/types'
import { config, US_BOUNDS } from '../config'
import { RouteLayers, type Hover, type MapLike } from './routeLayers'

interface Props {
  routes?: RoutesResponse
  risk?: RiskResponse
  selectedId: string | null
  onSelect: (routeId: string) => void
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

export function MapView({ routes, risk, selectedId, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const layers = useRef<RouteLayers | null>(null)
  const latestOnSelect = useRef(onSelect)

  useEffect(() => {
    latestOnSelect.current = onSelect
  }, [onSelect])

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
    const routeLayers = new RouteLayers(
      map as unknown as MapLike,
      (id) => latestOnSelect.current(id),
      popupHover(map),
      fitPadding,
      fitDuration,
    )
    layers.current = routeLayers
    map.on('load', () => routeLayers.ready())
    return () => {
      layers.current = null
      map.remove()
    }
  }, [])

  // Data and selection only update what is already there.
  const routeList = routes?.routes ?? NO_ROUTES
  const riskList = risk?.routes
  useEffect(() => {
    layers.current?.update({ routes: routeList, risk: riskList, selectedId })
  }, [routeList, riskList, selectedId])

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
