import { describe, expect, it } from 'vitest'
import { LEVEL_ORDER, LEVELS, contrastRatio } from '../src/levels'

describe('risk level styles', () => {
  it('names every level in words, in severity order', () => {
    expect(LEVEL_ORDER.map((l) => LEVELS[l].label)).toEqual([
      'Low',
      'Moderate',
      'High',
      'Severe',
      'No Travel',
      'No forecast',
    ])
  })

  it.each(LEVEL_ORDER)('%s text is readable on its colour (WCAG AA, 4.5:1)', (level) => {
    const { color, onColor } = LEVELS[level]
    expect(contrastRatio(color, onColor)).toBeGreaterThanOrEqual(4.5)
  })

  it('computes the standard contrast extremes', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0)
    expect(contrastRatio('#777777', '#777777')).toBeCloseTo(1, 5)
  })

  it('uses a distinct colour per level', () => {
    expect(new Set(LEVEL_ORDER.map((l) => LEVELS[l].color)).size).toBe(6)
  })
})
