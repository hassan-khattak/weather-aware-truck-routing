import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../src/App'
import { US_BOUNDS } from '../src/config'

const { Map: MapMock, remove } = vi.hoisted(() => ({
  Map: vi.fn(),
  remove: vi.fn(),
}))

// jsdom has no WebGL, so the real map cannot run here.
vi.mock('maplibre-gl', () => ({
  Map: MapMock.mockImplementation(function () {
    return { addControl: vi.fn(), remove }
  }),
  NavigationControl: vi.fn(),
}))

describe('App', () => {
  it('renders the map container and fits it to the continental US', () => {
    const { unmount } = render(<App />)

    expect(screen.getByTestId('map')).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Trip planner' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /weather-aware truck routing/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/open-meteo/i)).toBeInTheDocument() // attribution
    expect(MapMock).toHaveBeenCalledTimes(1)
    expect(MapMock.mock.calls[0][0]).toMatchObject({ bounds: US_BOUNDS })

    unmount()
    expect(remove).toHaveBeenCalled()
  })
})
