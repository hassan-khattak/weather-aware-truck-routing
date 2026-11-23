import { create } from 'zustand'
import type { RoutesRequest } from '../api/types'

interface UiState {
  /** The search being shown; null until the user submits the form. */
  request: RoutesRequest | null
  /** Changes on every submit, so searching again always fetches fresh data. */
  searchId: number
  selectedRouteId: string | null
  /** Form folded into a one-line summary after a search. */
  formCollapsed: boolean
  submit: (request: RoutesRequest) => void
  selectRoute: (id: string) => void
  setFormCollapsed: (collapsed: boolean) => void
  reset: () => void
}

const initial = { request: null, searchId: 0, selectedRouteId: null, formCollapsed: false }

export const useUiStore = create<UiState>((set) => ({
  ...initial,
  // A new search forgets the old selection and folds the form away.
  submit: (request) =>
    set((state) => ({
      request,
      searchId: state.searchId + 1,
      selectedRouteId: null,
      formCollapsed: true,
    })),
  selectRoute: (id) => set({ selectedRouteId: id }),
  setFormCollapsed: (collapsed) => set({ formCollapsed: collapsed }),
  reset: () => set(initial),
}))
