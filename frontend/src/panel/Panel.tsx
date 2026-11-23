import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

/**
 * Tells the map overlays how tall the bottom sheet is, so they can sit above it. On desktop the
 * panel is a side column and nothing overlaps, so the height is 0.
 */
function useSheetHeight(ref: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const root = document.documentElement
    const update = () => {
      const overlapping = getComputedStyle(el).position === 'absolute'
      root.style.setProperty('--sheet-h', overlapping ? `${el.offsetHeight}px` : '0px')
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    window.addEventListener('resize', update)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', update)
      root.style.removeProperty('--sheet-h')
    }
  }, [ref])
}

/**
 * The left panel on desktop (~380 px); a bottom sheet over the map on small screens, where a
 * handle folds it down to its title so the map and the time slider have room.
 */
export function Panel({ children }: { children?: ReactNode }) {
  const [open, setOpen] = useState(true)
  const body = useId()
  const sheet = useRef<HTMLElement>(null)
  useSheetHeight(sheet)

  return (
    <aside
      ref={sheet}
      aria-label="Trip planner"
      className="z-10 flex w-[380px] shrink-0 flex-col border-r border-line bg-panel max-md:absolute max-md:inset-x-0 max-md:bottom-0 max-md:max-h-[55%] max-md:w-full max-md:rounded-t-xl max-md:border-t max-md:border-r-0 max-md:shadow-[0_-4px_16px_rgba(0,0,0,0.15)]"
    >
      <header className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold">Weather-Aware Truck Routing</h1>
          <p className="text-sm text-muted">Pick the safest route for your load.</p>
        </div>
        <button
          type="button"
          aria-label={open ? 'Hide trip details' : 'Show trip details'}
          aria-expanded={open}
          aria-controls={body}
          onClick={() => setOpen(!open)}
          className="rounded-md border border-line px-2.5 py-1 text-sm focus:ring-2 focus:ring-accent/50 focus:outline-none md:hidden"
        >
          {open ? 'Hide' : 'Show'}
        </button>
      </header>
      <div id={body} className={`flex min-h-0 flex-1 flex-col ${open ? '' : 'max-md:hidden'}`}>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
        <footer className="border-t border-line px-4 py-2 text-xs text-muted">
          Weather by Open-Meteo · Routing by TomTom · Map data © OpenStreetMap contributors, tiles
          by OpenFreeMap · Places from GeoNames
        </footer>
      </div>
    </aside>
  )
}
