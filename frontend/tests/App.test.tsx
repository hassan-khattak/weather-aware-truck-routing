import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
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
    expect(fake.sources).toEqual([
      'checkpoint-highlight',
      'route-markers',
      'checkpoint-dots',
      'route-A',
      'route-B',
      'route-C',
    ])
    expect(fake.layers).toEqual([
      'checkpoint-highlight',
      'route-markers',
      'checkpoint-dots',
      'route-line-A',
      'route-line-B',
      'route-line-C',
    ])

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
    expect(fake.sources).toHaveLength(6) // three checkpoint sources, three routes
    expect(fake.layers).toHaveLength(6)
  })

  it('folds the form into a summary after a search and keeps the values when reopened', async () => {
    stubApi('A')
    renderApp()
    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))

    // The summary replaces the visible form; the form is only hidden.
    expect(await screen.findByText(/^Denver → Cheyenne · .* · 42,000 lb$/)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Plan a trip', hidden: true })).not.toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Edit trip' }))
    expect(screen.getByRole('form', { name: 'Plan a trip' })).toBeVisible()
    expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveValue('Denver, CO')
    expect(screen.getByRole('combobox', { name: 'Destination' })).toHaveValue('Cheyenne, WY')
  })

  it('reopens the form and shows the message when the search fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                code: 'NO_ROUTE',
                message: 'No truck route found between these places. Try a nearby city.',
              },
            }),
            { status: 422 },
          ),
      ),
    )
    renderApp()
    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))

    expect(
      await screen.findByText(/no truck route found between these places/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Plan a trip' })).toBeVisible() // ready to fix
  })

  it('keeps the cards and the map selection in sync', async () => {
    stubApi('B')
    renderApp()
    fake.handlers['load']()
    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))

    // Risk arrives: the recommended route (B) is selected on the card and on the map.
    const cardB = await screen.findByRole('button', { name: /^Route B/ })
    await waitFor(() => expect(cardB).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.getByTestId('recommendation')).toHaveTextContent('Recommended: Route B')
    expect(Array.isArray(fake.paint['route-line-B']['line-gradient'])).toBe(true)

    // Clicking card A selects it on the card list and on the map.
    await userEvent.click(screen.getByRole('button', { name: /^Route A/ }))
    expect(screen.getByRole('button', { name: /^Route A/ })).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() =>
      expect(Array.isArray(fake.paint['route-line-A']['line-gradient'])).toBe(true),
    )
    expect(fake.paint['route-line-B']['line-gradient']).toBeNull()

    // Clicking the line on the map selects the card.
    fake.handlers['click:route-line-B']()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^Route B/ })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    )
  })
})

/** Automated accessibility checks. Colour contrast needs real layout, so it is tested on the
 *  design tokens instead (tests/contrast.test.ts). */
async function expectNoViolations(container: HTMLElement) {
  const results = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  })
  expect(
    results.violations.map((v) => `${v.id}: ${v.help} (${v.nodes[0]?.html.slice(0, 80)})`),
  ).toEqual([])
}

describe('accessibility', () => {
  it('has no axe violations on the first screen', async () => {
    const { container } = renderApp()
    await expectNoViolations(container)
  })

  it('has no axe violations with results, cards and a recommendation', async () => {
    stubApi('B')
    const { container } = renderApp()
    fake.handlers['load']()
    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))
    await screen.findByTestId('recommendation')
    await expectNoViolations(container)
  })

  it('has no axe violations while showing form errors', async () => {
    const { container } = renderApp()
    await userEvent.click(screen.getByRole('button', { name: /find the safest route/i }))
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0)
    await expectNoViolations(container)
  })

  it('has no axe violations when a search fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { code: 'NO_ROUTE', message: 'No truck route found.' } }),
            {
              status: 422,
            },
          ),
      ),
    )
    const { container } = renderApp()
    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))
    await screen.findByText('No truck route found.')
    await expectNoViolations(container)
  })

  it('labels the map region', () => {
    renderApp()
    expect(screen.getByRole('region', { name: /map of the routes/i })).toBeInTheDocument()
  })

  it('tabs through the form in reading order', async () => {
    renderApp()
    const order = [
      screen.getByRole('combobox', { name: 'Origin' }),
      screen.getByRole('button', { name: /swap origin and destination/i }),
      screen.getByRole('combobox', { name: 'Destination' }),
      screen.getByLabelText(/^Departure/),
      screen.getByLabelText(/cargo weight/i),
      screen.getByRole('button', { name: /find the safest route/i }),
      screen.getByRole('button', { name: /denver → cheyenne/i }),
      screen.getByRole('button', { name: /salt lake city → denver/i }),
      screen.getByRole('button', { name: /chicago → dallas/i }),
      screen.getByRole('button', { name: /seattle → chicago/i }),
    ]
    for (const element of order) {
      await userEvent.tab()
      expect(element).toHaveFocus()
    }
  })

  it('moves focus to the results after a search', async () => {
    stubApi('A')
    renderApp()
    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))
    await waitFor(() =>
      expect(screen.getByRole('region', { name: 'Search results' })).toHaveFocus(),
    )
  })

  it('moves focus to the first invalid field when the form is rejected', async () => {
    renderApp()
    await userEvent.click(screen.getByRole('button', { name: /find the safest route/i }))
    expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveFocus()
  })

  it('puts the cursor back in the form when the trip is edited', async () => {
    stubApi('A')
    renderApp()
    await userEvent.click(screen.getByRole('button', { name: /denver → cheyenne/i }))
    await userEvent.click(await screen.findByRole('button', { name: 'Edit trip' }))
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveFocus())
  })
})
