import { LEVEL_ORDER, LEVELS, type Level } from '../levels'

type Miles = Record<Level, number>

/** The share of each level along a route as a stacked bar, with the same facts in words. */
export function riskSplitText(miles: Miles): string {
  const total = LEVEL_ORDER.reduce((sum, level) => sum + miles[level], 0)
  if (total <= 0) return 'No risk data'
  const parts = LEVEL_ORDER.filter((level) => miles[level] > 0).map((level) => {
    const percent = Math.max(Math.round((miles[level] / total) * 100), 1)
    return `${percent}% ${LEVELS[level].label}`
  })
  return `Risk split: ${parts.join(', ')}`
}

export function RiskBar({ miles }: { miles: Miles }) {
  const total = LEVEL_ORDER.reduce((sum, level) => sum + miles[level], 0)
  return (
    <div
      role="img"
      aria-label={riskSplitText(miles)}
      className="flex h-2.5 w-full overflow-hidden rounded-full bg-line"
    >
      {total > 0 &&
        LEVEL_ORDER.filter((level) => miles[level] > 0).map((level) => (
          <span
            key={level}
            style={{
              width: `${(miles[level] / total) * 100}%`,
              backgroundColor: LEVELS[level].color,
            }}
          />
        ))}
    </div>
  )
}
