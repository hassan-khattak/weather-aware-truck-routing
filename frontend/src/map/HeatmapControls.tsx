import { useState } from 'react'
import type { LayerName } from '../lib/heatmapDecode'
import { legendFor } from '../lib/ramps'
import { useUiStore } from '../state/uiStore'

const LAYERS: { id: LayerName; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'wind', label: 'Wind' },
  { id: 'rain', label: 'Rain' },
  { id: 'snow', label: 'Snow' },
]

/** Layer switch, show/hide toggle and legend for the weather glow. */
export function HeatmapControls() {
  const layer = useUiStore((s) => s.heatmapLayer)
  const visible = useUiStore((s) => s.heatmapVisible)
  const setLayer = useUiStore((s) => s.setHeatmapLayer)
  const setVisible = useUiStore((s) => s.setHeatmapVisible)
  const legend = legendFor(layer)
  // On phones the overlay folds into one button so it does not cover the map.
  const [open, setOpen] = useState(false)

  return (
    <section
      aria-label="Weather overlay"
      className="absolute top-3 left-3 z-10 w-56 max-md:w-40 rounded-lg bg-white/95 p-2.5 text-xs shadow-md"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="w-full rounded-md border border-line px-2 py-1 text-left font-medium focus:ring-2 focus:ring-accent/50 focus:outline-none md:hidden"
      >
        Weather {open ? '▴' : '▾'}
      </button>
      <div className={open ? 'max-md:mt-2' : 'max-md:hidden'}>
        <label className="flex items-center gap-1.5 font-medium">
          <input
            type="checkbox"
            checked={visible}
            onChange={(event) => setVisible(event.target.checked)}
          />
          Weather overlay
        </label>
        <div role="radiogroup" aria-label="Overlay layer" className="mt-2 grid grid-cols-4 gap-1">
          {LAYERS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={layer === id}
              disabled={!visible}
              onClick={() => setLayer(id)}
              className={`rounded-md border px-1 py-1 focus:ring-2 focus:ring-accent/50 focus:outline-none disabled:opacity-50 ${
                layer === id ? 'border-accent bg-accent/10 font-semibold' : 'border-line'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {visible && (
          <div className="mt-2" aria-label={`Legend: ${legend.title}`} role="group">
            <p className="text-muted">
              {legend.title}
              {legend.unit && ` (${legend.unit})`}
            </p>
            <ul className="mt-1 flex gap-1">
              {legend.stops.map((stop) => (
                <li key={stop.label} className="flex-1 text-center">
                  <span
                    aria-hidden="true"
                    className="block h-2.5 rounded-sm border border-line"
                    style={{ backgroundColor: stop.color }}
                  />
                  {stop.label}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}
