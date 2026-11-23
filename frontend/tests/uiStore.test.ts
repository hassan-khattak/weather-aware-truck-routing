import { beforeEach, describe, expect, it } from 'vitest'
import type { RoutesRequest } from '../src/api/types'
import { useUiStore } from '../src/state/uiStore'

const REQUEST: RoutesRequest = {
  origin: { label: 'A', lat: 1, lon: 2 },
  destination: { label: 'B', lat: 3, lon: 4 },
  departure_local: '2026-11-24T15:00',
  load_lb: 1000,
}

beforeEach(() => useUiStore.getState().reset())

describe('ui store', () => {
  it('starts empty with the form open', () => {
    expect(useUiStore.getState()).toMatchObject({
      request: null,
      searchId: 0,
      selectedRouteId: null,
      formCollapsed: false,
    })
  })

  it('a new search folds the form and forgets the previous selection', () => {
    useUiStore.getState().selectRoute('B')
    useUiStore.getState().submit(REQUEST)
    expect(useUiStore.getState()).toMatchObject({
      request: REQUEST,
      selectedRouteId: null,
      formCollapsed: true,
    })
  })

  it('every submit gets a new search id, even with identical input', () => {
    useUiStore.getState().submit(REQUEST)
    const first = useUiStore.getState().searchId
    useUiStore.getState().submit(REQUEST)
    expect(useUiStore.getState().searchId).toBe(first + 1)
  })

  it('selects routes and reopens the form', () => {
    useUiStore.getState().submit(REQUEST)
    useUiStore.getState().selectRoute('C')
    useUiStore.getState().setFormCollapsed(false)
    expect(useUiStore.getState()).toMatchObject({ selectedRouteId: 'C', formCollapsed: false })
  })
})
