import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Checkpoint } from '../../src/api/types'
import { CheckpointList } from '../../src/panel/CheckpointList'

function cp(idx: number, level: Checkpoint['level']): Checkpoint {
  return {
    idx,
    mile: idx * 25,
    lat: 35,
    lon: -101,
    eta_utc: '2026-11-25T02:40:00Z',
    tz: 'America/Chicago',
    road: 'I-40 W',
    town: 'Amarillo, TX',
    town_dist_mi: 2,
    town_dir: 'N',
    wind_mph: 5,
    gust_mph: 9,
    rain_in_hr: 0,
    snow_in_hr: 0,
    level,
    reasons: [],
    forecast: true,
  }
}

const POINTS = [cp(0, 'LOW'), cp(1, 'HIGH'), cp(2, 'MODERATE'), cp(3, 'SEVERE')]

describe('CheckpointList', () => {
  it('lists every checkpoint with its level in words', () => {
    render(<CheckpointList routeId="B" checkpoints={POINTS} activeIdx={null} onPick={vi.fn()} />)
    expect(screen.getAllByRole('button')).toHaveLength(4)
    const second = screen.getByRole('button', { name: /CP 2 · Mile 25/ })
    expect(second).toHaveTextContent('High')
    expect(second).toHaveTextContent('I-40 W near Amarillo, TX · Tue 8:40 PM CST')
  })

  it('reports which row was picked and marks the active one', async () => {
    const onPick = vi.fn()
    render(<CheckpointList routeId="B" checkpoints={POINTS} activeIdx={3} onPick={onPick} />)
    expect(screen.getByRole('button', { name: /CP 4/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /CP 1 / }))
    expect(onPick).toHaveBeenCalledWith(0)
  })

  it('announces the active checkpoint like the map tooltip does', () => {
    render(<CheckpointList routeId="B" checkpoints={POINTS} activeIdx={1} onPick={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent(
      'CP 2 · Mile 25 · I-40 W near Amarillo, TX. ETA Tue 8:40 PM CST. Wind 5 mph (gusts 9) · Rain 0 in/hr · Snow 0 in/hr. 🟠 HIGH',
    )
  })

  it('can show only High and above', async () => {
    render(<CheckpointList routeId="B" checkpoints={POINTS} activeIdx={null} onPick={vi.fn()} />)
    await userEvent.click(screen.getByRole('checkbox', { name: 'Show only High and above' }))
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      expect.stringContaining('CP 2'),
      expect.stringContaining('CP 4'),
    ])
  })

  it('says so when nothing is High or worse', async () => {
    render(
      <CheckpointList routeId="A" checkpoints={[cp(0, 'LOW')]} activeIdx={null} onPick={vi.fn()} />,
    )
    await userEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByText('No High or worse checkpoints on this route.')).toBeInTheDocument()
  })

  it('renders nothing without checkpoints', () => {
    const { container } = render(
      <CheckpointList routeId="A" checkpoints={[]} activeIdx={null} onPick={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
