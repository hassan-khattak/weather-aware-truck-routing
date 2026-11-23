/** Risk levels as the API names them, with words, colours and readable text colours.
 *  A level is always shown in words as well as colour (accessibility). */
export type Level = 'LOW' | 'MODERATE' | 'HIGH' | 'SEVERE' | 'NO_TRAVEL' | 'NO_FORECAST'

export interface LevelStyle {
  label: string
  /** Fill colour for dots, bars and swatches. */
  color: string
  /** Text colour that stays readable (WCAG AA) on `color`. */
  onColor: string
}

export const LEVELS: Record<Level, LevelStyle> = {
  LOW: { label: 'Low', color: '#1a7f37', onColor: '#ffffff' },
  MODERATE: { label: 'Moderate', color: '#f2c200', onColor: '#000000' },
  HIGH: { label: 'High', color: '#e8710a', onColor: '#000000' },
  SEVERE: { label: 'Severe', color: '#c62828', onColor: '#ffffff' },
  NO_TRAVEL: { label: 'No Travel', color: '#6a1b9a', onColor: '#ffffff' },
  NO_FORECAST: { label: 'No forecast', color: '#5f6672', onColor: '#ffffff' },
}

export const LEVEL_ORDER: Level[] = [
  'LOW',
  'MODERATE',
  'HIGH',
  'SEVERE',
  'NO_TRAVEL',
  'NO_FORECAST',
]

/** Levels that need attention: the "High and above" filter and the thicker dot ring. */
export const HIGH_AND_ABOVE: ReadonlySet<Level> = new Set<Level>(['HIGH', 'SEVERE', 'NO_TRAVEL'])

function channel(value: number): number {
  const v = value / 255
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16)
  return (
    0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
  )
}

/** WCAG contrast ratio between two #rrggbb colours (1 to 21). */
export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
