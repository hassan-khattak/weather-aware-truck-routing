import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { contrastRatio } from '../src/levels'

/** Reads the design tokens from index.css so the test follows the real palette. */
// Vitest blanks CSS imports, so read the stylesheet from disk.
const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')

function tokens(): Record<string, string> {
  return Object.fromEntries(
    [...css.matchAll(/--color-([a-z-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]),
  )
}

/** `fg` at `alpha` painted over `bg`, as #rrggbb (what Tailwind's `bg-x/20` looks like). */
function blend(fg: string, alpha: number, bg: string): string {
  const parse = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
  const mixed = parse(fg).map((c, i) => Math.round(c * alpha + parse(bg)[i] * (1 - alpha)))
  return `#${mixed.map((c) => c.toString(16).padStart(2, '0')).join('')}`
}

const AA = 4.5

describe('design token contrast (WCAG AA)', () => {
  const t = tokens()

  it('finds the palette in the stylesheet', () => {
    expect(Object.keys(t)).toEqual(
      expect.arrayContaining(['ink', 'muted', 'accent', 'severe', 'low', 'high-text', 'panel']),
    )
  })

  it.each([
    ['body text', 'ink', 'panel'],
    ['secondary text', 'muted', 'panel'],
    ['links and active text', 'accent', 'panel'],
    ['error text', 'severe', 'panel'],
    ['warning text', 'high-text', 'panel'],
    ['success marks', 'low', 'panel'],
  ])('%s is readable on the panel', (_name, fg, bg) => {
    expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(AA)
  })

  it('white text is readable on the primary button and on the red and green banners', () => {
    for (const bg of ['accent', 'severe', 'low']) {
      expect(contrastRatio('#ffffff', t[bg])).toBeGreaterThanOrEqual(AA)
    }
  })

  it('dark text is readable on the stale-weather banner (yellow at 20%)', () => {
    expect(contrastRatio(t.ink, blend(t.moderate, 0.2, t.panel))).toBeGreaterThanOrEqual(AA)
  })

  it('error text is readable on the error box (red at 5%)', () => {
    expect(contrastRatio(t.severe, blend(t.severe, 0.05, t.panel))).toBeGreaterThanOrEqual(AA)
  })
})
