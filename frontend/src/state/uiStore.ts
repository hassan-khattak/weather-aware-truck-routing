import { create } from 'zustand'
import type { RoutesRequest } from '../api/types'
import type { LayerName } from '../lib/heatmapDecode'

interface UiState {
  /** The search being shown; null until the user submits the form. */
  request: RoutesRequest | null
  /** IANA zone of the origin, for showing the departure time in the summary. */
  originTz: string | null
  /** Changes on every submit, so searching again always fetches fresh data. */
  searchId: number
  selectedRouteId: string | null
  /** Checkpoint (index on the selected route) pinned by a click on a dot or a list row. */
  activeCheckpoint: number | null
  /** Hours after departure shown on the map. Whole numbers; fractions only while playing. */
  hour: number
  playing: boolean
  heatmapLayer: LayerName
  heatmapVisible: boolean
  /** Form folded into a one-line summary after a search. */
  formCollapsed: boolean
  submit: (request: RoutesRequest, originTz: string) => void
  selectRoute: (id: string) => void
  setActiveCheckpoint: (idx: number | null) => void
  setHour: (hour: number) => void
  setPlaying: (playing: boolean) => void
  setHeatmapLayer: (layer: LayerName) => void
  setHeatmapVisible: (visible: boolean) => void
  setFormCollapsed: (collapsed: boolean) => void
  reset: () => void
}

const initial = {
  request: null,
  originTz: null,
  searchId: 0,
  selectedRouteId: null,
  activeCheckpoint: null,
  hour: 0,
  playing: false,
  heatmapLayer: 'risk' as LayerName,
  heatmapVisible: true,
  formCollapsed: false,
}

export const useUiStore = create<UiState>((set) => ({
  ...initial,
  // A new search forgets the old selection and folds the form away.
  submit: (request, originTz) =>
    set((state) => ({
      request,
      originTz,
      searchId: state.searchId + 1,
      selectedRouteId: null,
      activeCheckpoint: null,
      hour: 0,
      playing: false,
      formCollapsed: true,
    })),
  // Checkpoint numbers belong to one route, so switching routes clears the pinned one.
  selectRoute: (id) => set({ selectedRouteId: id, activeCheckpoint: null }),
  setActiveCheckpoint: (idx) => set({ activeCheckpoint: idx }),
  setHour: (hour) => set({ hour }),
  setPlaying: (playing) => set({ playing }),
  setHeatmapLayer: (layer) => set({ heatmapLayer: layer }),
  setHeatmapVisible: (visible) => set({ heatmapVisible: visible }),
  setFormCollapsed: (collapsed) => set({ formCollapsed: collapsed }),
  reset: () => set(initial),
}))
