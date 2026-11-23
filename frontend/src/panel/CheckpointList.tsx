import { useEffect, useRef, useState } from 'react'
import type { Checkpoint } from '../api/types'
import { etaText, placeText, tooltipLines } from '../lib/checkpointInfo'
import { HIGH_AND_ABOVE, LEVELS } from '../levels'

interface Props {
  routeId: string
  checkpoints: Checkpoint[]
  activeIdx: number | null
  onPick: (idx: number) => void
}

/** The selected route's checkpoints as a list that stays in step with the dots on the map. */
export function CheckpointList({ routeId, checkpoints, activeIdx, onPick }: Props) {
  const [onlyHigh, setOnlyHigh] = useState(false)
  const rows = onlyHigh ? checkpoints.filter((cp) => HIGH_AND_ABOVE.has(cp.level)) : checkpoints
  const activeRow = useRef<HTMLButtonElement>(null)

  // A pick on the map brings its row into view.
  useEffect(() => {
    activeRow.current?.scrollIntoView?.({ block: 'nearest' })
  }, [activeIdx])

  if (checkpoints.length === 0) return null
  const active = checkpoints.find((cp) => cp.idx === activeIdx)
  return (
    <section aria-label={`Checkpoints on Route ${routeId}`} className="mt-4">
      {/* What the map tooltip shows, for people who cannot see it. */}
      <p role="status" className="sr-only">
        {active ? tooltipLines(active).join('. ') : ''}
      </p>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-xs font-semibold tracking-wide text-muted uppercase">
          Checkpoints · Route {routeId}
        </h2>
        <label className="flex items-center gap-1.5 text-xs">
          <input
            type="checkbox"
            checked={onlyHigh}
            onChange={(event) => setOnlyHigh(event.target.checked)}
          />
          Show only High and above
        </label>
      </div>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">No High or worse checkpoints on this route.</p>
      ) : (
        <ol className="mt-2 max-h-72 space-y-1 overflow-y-auto">
          {rows.map((cp) => {
            const isActive = cp.idx === activeIdx
            const level = LEVELS[cp.level]
            return (
              <li key={cp.idx}>
                <button
                  type="button"
                  ref={isActive ? activeRow : undefined}
                  aria-pressed={isActive}
                  onClick={() => onPick(cp.idx)}
                  className={`block w-full rounded-md border px-2 py-1.5 text-left text-xs focus:ring-2 focus:ring-accent/50 focus:outline-none ${
                    isActive ? 'border-accent bg-accent/10' : 'border-line'
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">
                      CP {cp.idx + 1} · Mile {Math.round(cp.mile)}
                    </span>
                    <span className="flex items-center gap-1">
                      <span
                        aria-hidden="true"
                        className="inline-block size-2.5 rounded-full"
                        style={{ backgroundColor: level.color }}
                      />
                      {level.label}
                    </span>
                  </span>
                  <span className="block text-muted">
                    {[placeText(cp), etaText(cp).replace('ETA ', '')].filter(Boolean).join(' · ')}
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
