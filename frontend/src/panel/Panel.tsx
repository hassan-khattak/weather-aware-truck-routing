import type { ReactNode } from 'react'

/** The left panel on desktop (~380 px); a bottom sheet over the map on small screens. */
export function Panel({ children }: { children?: ReactNode }) {
  return (
    <aside
      aria-label="Trip planner"
      className="z-10 flex w-[380px] shrink-0 flex-col border-r border-line bg-panel max-md:absolute max-md:inset-x-0 max-md:bottom-0 max-md:max-h-[55%] max-md:w-full max-md:rounded-t-xl max-md:border-t max-md:border-r-0 max-md:shadow-[0_-4px_16px_rgba(0,0,0,0.15)]"
    >
      <header className="border-b border-line px-4 py-3">
        <h1 className="text-lg font-semibold">Weather-Aware Truck Routing</h1>
        <p className="text-sm text-muted">Pick the safest route for your load.</p>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
      <footer className="border-t border-line px-4 py-2 text-xs text-muted">
        Weather by Open-Meteo · Routing by TomTom · Map data © OpenStreetMap contributors, tiles by
        OpenFreeMap · Places from GeoNames
      </footer>
    </aside>
  )
}
