import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Panel } from '../../src/panel/Panel'

describe('Panel on phones', () => {
  it('folds the details down to the title and back, announcing its state', async () => {
    render(
      <Panel>
        <p>Trip details</p>
      </Panel>,
    )
    const toggle = screen.getByRole('button', { name: /hide trip details/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Trip details')).toBeVisible()

    await userEvent.click(toggle)
    expect(screen.getByRole('button', { name: /show trip details/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.getByText('Trip details').closest('[id]')).toHaveClass('max-md:hidden')
    expect(
      screen.getByRole('heading', { name: /weather-aware truck routing/i }),
    ).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /show trip details/i }))
    expect(screen.getByText('Trip details').closest('[id]')).not.toHaveClass('max-md:hidden')
  })
})
