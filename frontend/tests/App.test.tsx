import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'
import { US_BOUNDS } from '../src/config'
import { useUiStore } from '../src/state/uiStore'
import { makeRisk, makeRoutes } from './fixtures'

// jsdom has no WebGL, so the real map cannot run here. This fake records what the app asks of it.
const fake = vi.hoisted(() => {
  const state = {
    constructed: [] as unknown[],
    removed: 0,
    handlers: {} as Record<string, (event?: unknown) => void>,
    sources: [] as string[],
    layers: [] as string[],
    data: {} as Record<string, unknown>,
    paint: {} as Record<string, Record<string, unknown>>,
  }
  return state
})

vi.mock('maplibre-gl', () => {
  class Map {
    constructor(options: unknown) {
      fake.constructed.push(options)
    }
    addControl() {}
    remove() {
      fake.removed += 1
    }
    on(type: string, a: unknown, b?: unknown) {
      const key = typeof a === 'string' ? `${type}:${a}` : type
      fake.handlers[key] = (typeof a === 'function' ? a : b) as (event?: unknown) => void
    }
    addSource(id: string) {
      fake.sources.push(id)
    }
    addLayer(layer: { id: string }) {
      fake.layers.push(layer.id)
    }
    getSource(id: string) {
      return { setData: (data: unknown) => (fake.data[id] = data) }
    }
    setPaintProperty(layer: string, name: string, value: unknown) {
      ;(fake.paint[layer] ??= {})[name] = value
    }
    moveLayer() {}
    fitBounds() {}
    getCanvas() {
      return { style: { cursor: '' } }
    }
  }
  class Popup {
    setLngLat() {
      return this
    }
    setDOMContent() {
      return this
    }
    addTo() {
      return this
    }
    remove() {}
  }
  return { Map, Popup, NavigationControl: class {} }
})

function stubApi(recommended: string) {
  const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/v1/routes') return json(makeRoutes())
      if (url === '/api/v1/risk') return json(makeRisk(recommended))
      return json([])
    }),
  )
}

function renderApp() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <App />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  useUiStore.getState().reset()
  Object.assign(fake, {
    constructed: [],
    removed: 0,
    handlers: {},
    sources: [],
    layers: [],
    data: {},
    paint: {},
  })
})

describe('App', () => {
  it('renders the panel, the attribution and a map fitted to the continental US', () => {
    const { unmount } = renderApp()

    expect(screen.getByTestId('map')).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Trip planner' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /weather-aware truck routing/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/open-meteo/i)).toBeInTheDocument()
    expect(fake.constructed).toHaveLength(1)
    expect(fake.constructed[0]).toMatchObject({ bounds: US_BOUNDS })

    unmount()
    expect(fake.removed).toBe(1)
  })

  it('draws the routes, colours the recommended one by risk, and switches on click without re-adding layers', async () => {
    stubApi('B')
    renderApp()
    fake.handlers['load']() // the map style has loaded
    expect(fake.sources).toEqual(['route-A', 'route-B', 'route-C'])
    expect(fake.layers).toEqual(['route-line-A', 'route-line-B', 'route-line-C'])

    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))

    // Routes appear first...
    await waitFor(() =>
      expect(fake.data['route-A']).toMatchObject({ geometry: { type: 'LineString' } }),
    )
    expect(fake.data['route-B']).toMatchObject({ geometry: { type: 'LineString' } })
    expect(fake.data['route-C']).toMatchObject({ features: [] })
    // ...then risk arrives and the RECOMMENDED route (B) gets the risk gradient.
    await waitFor(() =>
      expect(Array.isArray(fake.paint['route-line-B']?.['line-gradient'])).toBe(true),
    )
    expect(fake.paint['route-line-A']['line-gradient']).toBeNull()

    // Clicking route A moves the selection and the gradient.
    fake.handlers['click:route-line-A']()
    await waitFor(() =>
      expect(Array.isArray(fake.paint['route-line-A']['line-gradient'])).toBe(true),
    )
    expect(fake.paint['route-line-B']['line-gradient']).toBeNull()

    // Nothing was ever added again.
    expect(fake.sources).toHaveLength(3)
    expect(fake.layers).toHaveLength(3)
  })
})
