import { MapView } from './map/MapView'
import { Panel } from './panel/Panel'
import { TripForm } from './panel/TripForm'
import { useUiStore } from './state/uiStore'

export default function App() {
  const submit = useUiStore((state) => state.submit)
  return (
    <main className="relative flex h-full w-full overflow-hidden">
      <Panel>
        <TripForm onSubmit={submit} />
      </Panel>
      <div className="relative min-w-0 flex-1">
        <MapView />
      </div>
    </main>
  )
}
