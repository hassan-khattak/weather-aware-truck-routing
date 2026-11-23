import type { RiskResponse, Route, RouteRisk, RoutesResponse } from '../api/types'
import { formatDuration, formatMiles } from '../lib/format'
import { LEVEL_ORDER, LEVELS } from '../levels'
import { RiskBar } from './RiskBar'

const LONG_RANGE_NOTE =
  'Later part of this trip uses long-range forecasts; check again closer to departure.'

interface Props {
  trip: RoutesResponse
  risk: RiskResponse | undefined
  selectedId: string | null
  onSelect: (routeId: string) => void
}

/** Banners, the recommendation, and one card per route. */
export function RouteCards({ trip, risk, selectedId, onSelect }: Props) {
  const recommendation = risk?.recommendation
  return (
    <section aria-label="Routes" className="mt-4 space-y-3">
      {recommendation?.all_unsafe && (
        <p role="alert" className="rounded-md bg-severe px-3 py-2 text-sm font-medium text-white">
          No safe route at this departure time. Consider delaying.
        </p>
      )}
      {recommendation?.all_clear && (
        <p role="status" className="rounded-md bg-low px-3 py-2 text-sm font-medium text-white">
          All routes clear for this departure.
        </p>
      )}

      {recommendation && (
        <p className="text-sm font-medium" data-testid="recommendation">
          ⭐ Recommended: Route {recommendation.route_id}. {recommendation.reason}.
        </p>
      )}

      {trip.warnings.map((warning) => (
        <p key={warning} role="note" className="text-xs text-high-text">
          {warning}
        </p>
      ))}
      {trip.notes.map((note) => (
        <p key={note} className="text-xs text-muted">
          {note}
        </p>
      ))}
      <p className="text-xs text-muted">Weather sampled every {trip.interval_mi} mi</p>

      <ul className="space-y-2">
        {trip.routes.map((route) => (
          <li key={route.id}>
            <Card
              route={route}
              risk={risk?.routes.find((r) => r.id === route.id)}
              riskKnown={risk !== undefined}
              selected={route.id === selectedId}
              recommended={route.id === recommendation?.route_id}
              onSelect={() => onSelect(route.id)}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

interface CardProps {
  route: Route
  risk: RouteRisk | undefined
  riskKnown: boolean
  selected: boolean
  recommended: boolean
  onSelect: () => void
}

function Card({ route, risk, riskKnown, selected, recommended, onSelect }: CardProps) {
  const border = selected ? 'border-accent ring-2 ring-accent/30' : 'border-line'
  return (
    <div className={`rounded-lg border bg-white ${border}`}>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="block w-full rounded-lg px-3 py-2 text-left focus:ring-2 focus:ring-accent/50 focus:outline-none"
      >
        <span className="flex items-baseline justify-between gap-2">
          <span className="font-semibold">
            Route {route.id}
            {recommended && (
              <span className="ml-2 text-xs font-medium text-accent">⭐ Recommended</span>
            )}
            {route.source === 'generated' && (
              <span className="ml-2 text-xs font-normal text-muted">Alternative</span>
            )}
          </span>
          <span className="text-sm">
            {formatDuration(route.total_s)} · {formatMiles(route.distance_mi)}
          </span>
        </span>
        <span className="mt-2 block">
          {risk ? (
            <RiskBar miles={risk.summary.miles} />
          ) : (
            <span className="block text-xs text-muted">
              {riskKnown ? 'Risk not available for this route' : 'Weather risk: checking…'}
            </span>
          )}
        </span>
      </button>

      {selected && <Details route={route} risk={risk} />}
    </div>
  )
}

function Details({ route, risk }: { route: Route; risk: RouteRisk | undefined }) {
  const breaks = route.stops.filter((s) => s.type === 'break').length
  const rests = route.stops.filter((s) => s.type === 'rest').length
  const stops = [
    breaks > 0 ? `${breaks} break${breaks === 1 ? '' : 's'}` : null,
    rests > 0 ? `${rests} rest${rests === 1 ? '' : 's'}` : null,
  ].filter(Boolean)

  return (
    <div className="space-y-1 border-t border-line px-3 py-2 text-sm">
      <p>
        Driving {formatDuration(route.drive_s)} · Total {formatDuration(route.total_s)}
        {route.stops.length > 0 && ' incl. required rest'}
      </p>
      {stops.length > 0 && <p className="text-muted">Stops: {stops.join(', ')}</p>}
      {risk && (
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs" aria-label="Miles by risk level">
          {LEVEL_ORDER.filter((level) => risk.summary.miles[level] > 0).map((level) => (
            <li key={level} className="flex items-center gap-1">
              <span
                aria-hidden="true"
                className="inline-block size-2.5 rounded-full"
                style={{ backgroundColor: LEVELS[level].color }}
              />
              {LEVELS[level].label} {Math.round(risk.summary.miles[level]).toLocaleString('en-US')}{' '}
              mi
            </li>
          ))}
        </ul>
      )}
      {route.long_range_forecast && <p className="text-xs text-high-text">{LONG_RANGE_NOTE}</p>}
    </div>
  )
}
