import { MapView } from './map/MapView'
import { Panel } from './panel/Panel'

export default function App() {
  return (
    <main className="relative flex h-full w-full overflow-hidden">
      <Panel />
      <div className="relative min-w-0 flex-1">
        <MapView />
      </div>
    </main>
  )
}
