import { useTrip } from './api/hooks'
import { MapView } from './map/MapView'
import { Panel } from './panel/Panel'
import { TripForm } from './panel/TripForm'
import { resolveSelectedId } from './state/selection'
import { useUiStore } from './state/uiStore'

export default function App() {
  const { request, searchId, selectedRouteId, submit, selectRoute } = useUiStore()
  const { routes, risk } = useTrip(request, searchId)
  const selectedId = resolveSelectedId(selectedRouteId, routes.data, risk.data)

  return (
    <main className="relative flex h-full w-full overflow-hidden">
      <Panel>
        <TripForm onSubmit={submit} />
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
