import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { TimeSlider } from '../../src/map/TimeSlider'
import { useUiStore } from '../../src/state/uiStore'
import { LINE_A, makeRoute } from '../fixtures'

afterEach(() => useUiStore.getState().reset())

const route = makeRoute('A', LINE_A, { total_s: 20 * 3600, drive_s: 18 * 3600 })

function setup(hours = 49, r = route) {
  let parentRenders = 0
  function Parent() {
    parentRenders += 1
    return (
      <TimeSlider startUtc="2026-11-24T21:00:00Z" tz="America/Chicago" hours={hours} route={r} />
    )
  }
  render(<Parent />)
  return {
    renders: () => parentRenders,
    slider: screen.getByRole('slider', { name: 'Hours after departure' }),
  }
}

describe('TimeSlider', () => {
  it('shows the real time in the origin zone and follows the store', () => {
    setup()
    expect(screen.getByText('+0h · Tue 3:00 PM CST')).toBeInTheDocument()
    act(() => useUiStore.getState().setHour(6))
    expect(screen.getByText('+6h · Tue 9:00 PM CST')).toBeInTheDocument()
    expect(screen.getByRole('slider')).toHaveValue('6')
    expect(screen.getByRole('slider')).toHaveAttribute('aria-valuetext', '+6h · Tue 9:00 PM CST')
  })

  it('never re-renders the component tree above it while the hour changes', () => {
    const { renders } = setup()
    act(() => {
      for (let h = 1; h <= 30; h++) useUiStore.getState().setHour(h)
    })
    expect(renders()).toBe(1)
    expect(screen.getByText('+30h · Wed 9:00 PM CST')).toBeInTheDocument()
  })

  it('moves an hour with the arrow keys and six hours with Shift', async () => {
    const { slider } = setup()
    slider.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(useUiStore.getState().hour).toBe(1)
    await userEvent.keyboard('{Shift>}{ArrowRight}{/Shift}')
    expect(useUiStore.getState().hour).toBe(7)
    await userEvent.keyboard('{Shift>}{ArrowLeft}{ArrowLeft}{/Shift}')
    expect(useUiStore.getState().hour).toBe(0) // clamped at the start
    await userEvent.keyboard('{Shift>}{ArrowUp}{/Shift}')
    expect(useUiStore.getState().hour).toBe(6)
    await userEvent.keyboard('{End}')
    expect(useUiStore.getState().hour).toBe(48)
    await userEvent.keyboard('{Home}')
    expect(useUiStore.getState().hour).toBe(0)
  })

  it('stops at the end of the forecast window and takes over from Play', async () => {
    const { slider } = setup()
    useUiStore.getState().setPlaying(true)
    act(() => useUiStore.getState().setHour(47))
    slider.focus()
    await userEvent.keyboard('{Shift>}{ArrowRight}{/Shift}')
    expect(useUiStore.getState().hour).toBe(48)
    expect(useUiStore.getState().playing).toBe(false)
  })

  it('says when the truck has arrived or the trip outlasts the forecast', () => {
    setup()
    act(() => useUiStore.getState().setHour(30))
    expect(screen.getByRole('status')).toHaveTextContent('Arrived')

    const long = makeRoute('A', LINE_A, {
      distance_mi: 3000,
      total_s: 80 * 3600,
      drive_s: 60 * 3600,
      timeline: [
        [0, 0],
        [80 * 3600, 3000],
      ],
    })
    document.body.innerHTML = ''
    setup(49, long)
    act(() => useUiStore.getState().setHour(48))
    expect(screen.getByRole('status')).toHaveTextContent('Trip continues beyond forecast window')
  })
})
