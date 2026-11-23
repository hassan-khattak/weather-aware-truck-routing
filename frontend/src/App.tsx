import { useTrip } from './api/hooks'
import { serverFieldErrors } from './lib/serverErrors'
import { MapView } from './map/MapView'
import { Panel } from './panel/Panel'
import { RouteCards } from './panel/RouteCards'
import { SearchStatus } from './panel/SearchStatus'
import { TripForm } from './panel/TripForm'
import { TripSummary } from './panel/TripSummary'
import { resolveSelectedId } from './state/selection'
import { useUiStore } from './state/uiStore'

export default function App() {
  const { request, originTz, searchId, selectedRouteId, formCollapsed } = useUiStore()
  const { submit, selectRoute, setFormCollapsed } = useUiStore()
  const { routes, risk } = useTrip(request, searchId)
  const selectedId = resolveSelectedId(selectedRouteId, routes.data, risk.data)

  // A failed search reopens the form so the problem can be fixed; otherwise it folds to a summary.
  const collapsed = formCollapsed && request !== null && !routes.isError

  return (
    <main className="relative flex h-full w-full overflow-hidden">
      <Panel>
        {collapsed && request && originTz && (
          <TripSummary request={request} tz={originTz} onEdit={() => setFormCollapsed(false)} />
        )}
        {/* Hidden, not removed, so the values are kept when the form is reopened. */}
        <div hidden={collapsed}>
          <TripForm onSubmit={submit} serverErrors={serverFieldErrors(routes.error)} />
        </div>
        <SearchStatus searched={request !== null} routes={routes} risk={risk} />
        {routes.data && (
          <RouteCards
            trip={routes.data}
            risk={risk.data}
            selectedId={selectedId}
            onSelect={selectRoute}
          />
        )}
      </Panel>
      <div className="relative min-w-0 flex-1">
        <MapView
          routes={routes.data}
          risk={risk.data}
          selectedId={selectedId}
          onSelect={selectRoute}
        />
      </div>
    </main>
  )
}
