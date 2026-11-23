import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { HeatmapControls } from '../../src/map/HeatmapControls'
import { useUiStore } from '../../src/state/uiStore'

afterEach(() => useUiStore.getState().reset())

describe('HeatmapControls', () => {
  it('switches the layer and shows a legend with units', async () => {
    render(<HeatmapControls />)
    expect(screen.getByRole('radio', { name: 'Risk' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('group', { name: 'Legend: Risk for this truck' })).toHaveTextContent(
      'Severe',
    )
    await userEvent.click(screen.getByRole('radio', { name: 'Wind' }))
    expect(useUiStore.getState().heatmapLayer).toBe('wind')
    expect(screen.getByRole('group', { name: 'Legend: Wind' })).toHaveTextContent('mph')
  })

  it('hides the overlay and its legend with the toggle', async () => {
    render(<HeatmapControls />)
    await userEvent.click(screen.getByRole('checkbox', { name: 'Weather overlay' }))
    expect(useUiStore.getState().heatmapVisible).toBe(false)
    expect(screen.queryByRole('group', { name: /Legend/ })).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Snow' })).toBeDisabled()
  })
})

describe('HeatmapControls on phones', () => {
  it('folds into one button that opens and closes the controls', async () => {
    render(<HeatmapControls />)
    const toggle = screen.getByRole('button', { name: /^Weather/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })
})
