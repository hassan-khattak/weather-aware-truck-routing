import { setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

// By default MapLibre looks for its worker file next to the library file. Once the app is bundled
// that file does not exist, the worker fails to load, and no route, dot or heatmap is ever drawn
// (the basemap still appears, which hides the problem). Vite emits the worker as its own asset
// here, and MapLibre is told where it is. Import this before creating a map.
setWorkerUrl(workerUrl)
