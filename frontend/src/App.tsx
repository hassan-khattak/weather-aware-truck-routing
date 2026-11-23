import { useEffect, useRef } from 'react'
import { useTrip } from './api/hooks'
import { serverFieldErrors } from './lib/serverErrors'
import { HeatmapControls } from './map/HeatmapControls'
import { TimeSlider } from './map/TimeSlider'
import { MapView } from './map/MapView'
import { Panel } from './panel/Panel'
import { CheckpointList } from './panel/CheckpointList'
import { RouteCards } from './panel/RouteCards'
import { SearchStatus } from './panel/SearchStatus'
import { TripForm } from './panel/TripForm'
import { TripSummary } from './panel/TripSummary'
import { resolveSelectedId } from './state/selection'
import { useUiStore } from './state/uiStore'

export default function App() {
  const { request, originTz, searchId, selectedRouteId, formCollapsed } = useUiStore()
  const { submit, selectRoute, setFormCollapsed, activeCheckpoint, setActiveCheckpoint } =
    useUiStore()
  const { routes, risk } = useTrip(request, searchId)
  const selectedId = resolveSelectedId(selectedRouteId, routes.data, risk.data)
  const selectedRisk = risk.data?.routes.find((r) => r.id === selectedId)
  const results = useRef<HTMLDivElement>(null)
  const formArea = useRef<HTMLDivElement>(null)

  // After a search the form folds away, so keyboard focus moves to the results area.
  useEffect(() => {
    if (searchId > 0) results.current?.focus()
  }, [searchId])

  function editTrip() {
    setFormCollapsed(false)
    // Wait for the form to be shown again, then put the cursor in its first field.
    requestAnimationFrame(() => formArea.current?.querySelector('input')?.focus())
  }

  // A failed search reopens the form so the problem can be fixed; otherwise it folds to a summary.
  const collapsed = formCollapsed && request !== null && !routes.isError

  return (
    <main className="relative flex h-full w-full overflow-hidden">
      <Panel>
        {collapsed && request && originTz && (
          <TripSummary request={request} tz={originTz} onEdit={editTrip} />
        )}
        {/* Hidden, not removed, so the values are kept when the form is reopened. */}
        <div ref={formArea} hidden={collapsed}>
          <TripForm onSubmit={submit} serverErrors={serverFieldErrors(routes.error)} />
        </div>
        <div
          ref={results}
          tabIndex={-1}
          role="region"
          aria-label="Search results"
          className="outline-none"
        >
          <SearchStatus searched={request !== null} routes={routes} risk={risk} />
          {routes.data && (
            <RouteCards
              trip={routes.data}
              risk={risk.data}
              riskFailed={risk.isError}
              selectedId={selectedId}
              onSelect={selectRoute}
            />
          )}
          {selectedRisk && selectedId && (
            <CheckpointList
              routeId={selectedId}
              checkpoints={selectedRisk.checkpoints}
              activeIdx={activeCheckpoint}
              onPick={setActiveCheckpoint}
            />
          )}
        </div>
      </Panel>
      <div className="relative min-w-0 flex-1">
        <MapView
          routes={routes.data}
          risk={risk.data}
          selectedId={selectedId}
          onSelect={selectRoute}
          activeCheckpoint={activeCheckpoint}
          onPickCheckpoint={setActiveCheckpoint}
        />
        {risk.data && <HeatmapControls />}
        {risk.data && routes.data && risk.data.heatmap.hours > 0 && (
          <TimeSlider
            startUtc={risk.data.heatmap.start_utc}
            tz={routes.data.departure.tz}
            hours={risk.data.heatmap.hours}
            route={routes.data.routes.find((r) => r.id === selectedId)}
          />
        )}
      </div>
    </main>
  )
}
