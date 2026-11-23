import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RiskResponse, RoutesResponse } from '../../src/api/types'
import { riskSplitText } from '../../src/panel/RiskBar'
import { RouteCards } from '../../src/panel/RouteCards'
import { LINE_A, makeRisk, makeRoute, makeRoutes } from '../fixtures'

function setup(
  over: { trip?: RoutesResponse; risk?: RiskResponse | undefined; selectedId?: string | null } = {},
) {
  const onSelect = vi.fn()
  const trip = over.trip ?? makeRoutes()
  const risk = 'risk' in over ? over.risk : makeRisk('B')
  render(
    <RouteCards trip={trip} risk={risk} selectedId={over.selectedId ?? 'B'} onSelect={onSelect} />,
  )
  return { onSelect, user: userEvent.setup() }
}

describe('cards', () => {
  it('shows each route with its time, distance and risk split', () => {
    setup()
    const card = screen.getByRole('button', { name: /^Route A/ })
    expect(card).toHaveTextContent('1h 55m · 109 mi')
    expect(within(card).getByRole('img')).toHaveAccessibleName(/risk split: 50% low, 50% high/i)
  })

  it('marks the recommended route with a badge and states the reason', () => {
    setup()
    expect(screen.getByRole('button', { name: /^Route B/ })).toHaveTextContent('⭐ Recommended')
    expect(screen.getByTestId('recommendation')).toHaveTextContent(
      '⭐ Recommended: Route B. 0 Severe mi vs 25 on Route X; +18 min.',
    )
  })

  it('expands only the selected card', () => {
    setup({ selectedId: 'B' })
    expect(screen.getByRole('button', { name: /^Route B/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /^Route A/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    expect(screen.getAllByText(/^Driving /)).toHaveLength(1)
  })

  it('selects a route when its card is clicked', async () => {
    const { onSelect, user } = setup({ selectedId: 'B' })
    await user.click(screen.getByRole('button', { name: /^Route A/ }))
    expect(onSelect).toHaveBeenCalledWith('A')
  })

  it('marks generated alternatives as such', () => {
    const trip = makeRoutes()
    trip.routes[1] = makeRoute('B', LINE_A, { source: 'generated' })
    setup({ trip })
    expect(screen.getByRole('button', { name: /^Route B/ })).toHaveTextContent('Alternative')
  })
})

describe('expanded card', () => {
  it('shows driving and total time, saying when rest is included', () => {
    const trip = makeRoutes()
    trip.routes[0] = makeRoute('A', LINE_A, {
      drive_s: 16 * 3600,
      total_s: 26.5 * 3600,
      stops: [
        { type: 'break', mile: 400, start_utc: '2026-11-25T05:00:00Z', duration_s: 1800 },
        { type: 'rest', mile: 650, start_utc: '2026-11-25T08:00:00Z', duration_s: 36000 },
      ],
    })
    setup({ trip, selectedId: 'A' })
    expect(screen.getByText('Driving 16h · Total 26h 30m incl. required rest')).toBeInTheDocument()
    expect(screen.getByText('Stops: 1 break, 1 rest')).toBeInTheDocument()
  })

  it('does not mention rest when there are no stops', () => {
    setup({ selectedId: 'A' })
    expect(screen.getByText('Driving 1h 55m · Total 1h 55m')).toBeInTheDocument()
  })

  it('lists miles by risk level in words', () => {
    setup({ selectedId: 'A' })
    const list = screen.getByRole('list', { name: 'Miles by risk level' })
    expect(list).toHaveTextContent('Low 54 mi')
    expect(list).toHaveTextContent('High 54 mi')
    expect(list).not.toHaveTextContent('Severe') // zero-mile levels are left out
  })

  it('adds the long-range forecast note for trips reaching past reliable forecasts', () => {
    const trip = makeRoutes()
    trip.routes[0] = makeRoute('A', LINE_A, { long_range_forecast: true })
    setup({ trip, selectedId: 'A' })
    expect(
      screen.getByText(/long-range forecasts; check again closer to departure/i),
    ).toBeInTheDocument()
  })
})

describe('above the cards', () => {
  it('says how often weather is sampled, once', () => {
    setup()
    expect(screen.getAllByText('Weather sampled every 10 mi')).toHaveLength(1)
  })

  it('shows notes and warnings from the trip', () => {
    const trip = makeRoutes()
    trip.notes = ['2 distinct truck routes found for this trip.']
    trip.warnings = [
      'Exceeds typical legal cargo for a 5-axle tractor-trailer; truck routes may be restricted.',
    ]
    setup({ trip })
    expect(screen.getByText('2 distinct truck routes found for this trip.')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(/exceeds typical legal cargo/i)
  })

  it('shows the red banner when every route has No-Travel miles', () => {
    const risk = makeRisk('A')
    risk.recommendation.all_unsafe = true
    setup({ risk })
    expect(screen.getByRole('alert')).toHaveTextContent(
      'No safe route at this departure time. Consider delaying.',
    )
  })

  it('shows the green note when everything is clear', () => {
    const risk = makeRisk('A')
    risk.recommendation.all_clear = true
    setup({ risk })
    expect(screen.getByRole('status')).toHaveTextContent('All routes clear for this departure.')
  })

  it('shows no banner for mixed conditions', () => {
    setup()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('before risk is known', () => {
  it('never shows a risk bar or a recommendation, only that weather is being checked', () => {
    setup({ risk: undefined })
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByTestId('recommendation')).not.toBeInTheDocument()
    expect(screen.getAllByText('Weather risk: checking…')).toHaveLength(2)
    expect(screen.queryByText(/low/i)).not.toBeInTheDocument() // unknown is never shown as safe
  })

  it('still lets the driver compare and select routes by time and distance', async () => {
    const { onSelect, user } = setup({ risk: undefined, selectedId: 'A' })
    await user.click(screen.getByRole('button', { name: /^Route B/ }))
    expect(onSelect).toHaveBeenCalledWith('B')
  })
})

describe('riskSplitText', () => {
  const none = { LOW: 0, MODERATE: 0, HIGH: 0, SEVERE: 0, NO_TRAVEL: 0, NO_FORECAST: 0 }

  it('describes the split in words and percentages', () => {
    expect(riskSplitText({ ...none, LOW: 700, HIGH: 200, NO_FORECAST: 100 })).toBe(
      'Risk split: 70% Low, 20% High, 10% No forecast',
    )
  })

  it('never rounds a present level down to nothing', () => {
    expect(riskSplitText({ ...none, LOW: 1000, SEVERE: 0.5 })).toBe(
      'Risk split: 100% Low, 1% Severe',
    )
  })

  it('handles no data', () => {
    expect(riskSplitText(none)).toBe('No risk data')
  })
})

describe('when the weather step failed', () => {
  it('says the risk is unavailable instead of waiting forever or showing a safe bar', () => {
    render(
      <RouteCards
        trip={makeRoutes()}
        risk={undefined}
        riskFailed
        selectedId="A"
        onSelect={() => {}}
      />,
    )
    expect(screen.getAllByText('Weather risk unavailable')).toHaveLength(2)
    expect(screen.queryByText(/checking/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument() // no risk bar at all
  })
})
