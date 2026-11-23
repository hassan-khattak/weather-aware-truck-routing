import { Popup, type Map } from 'maplibre-gl'
import type { Checkpoint } from '../api/types'
import { tooltipLines } from '../lib/checkpointInfo'

export interface CheckpointTooltip {
  show(cp: Checkpoint, note: string | null): void
  hide(): void
}

/** One popup, reused. All text goes in with textContent: road and town names are data. */
export function checkpointTooltip(map: Map): CheckpointTooltip {
  const popup = new Popup({
    closeButton: false,
    closeOnClick: false,
    offset: 14,
    maxWidth: '320px',
  })
  return {
    show(cp, note) {
      const content = document.createElement('div')
      content.className = 'text-xs space-y-0.5'
      const lines = tooltipLines(cp)
      if (note) lines.push(note)
      lines.forEach((text, index) => {
        const row = document.createElement('div')
        row.textContent = text
        if (index === 0) row.className = 'font-semibold'
        if (note && index === lines.length - 1) row.className = 'text-muted italic'
        content.append(row)
      })
      popup.setLngLat([cp.lon, cp.lat]).setDOMContent(content).addTo(map)
    },
    hide() {
      popup.remove()
    },
  }
}
