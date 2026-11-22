import { Map, NavigationControl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import { config, US_BOUNDS } from '../config'

export function MapView() {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    // Created once; later phases add layers to this single instance.
    const map = new Map({
      container: container.current,
      style: config.mapStyleUrl,
      bounds: US_BOUNDS,
      fitBoundsOptions: { padding: 20 },
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    return () => map.remove()
  }, [])

  return <div ref={container} className="map" data-testid="map" />
}
