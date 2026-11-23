import type { UseQueryResult } from '@tanstack/react-query'
import { friendlyMessage } from '../api/client'
import type { RiskResponse, RoutesResponse } from '../api/types'
import { relativeAge } from '../lib/age'
import { totalCheckpoints } from '../lib/checkpoints'
import { isRetryable } from '../lib/serverErrors'

type Mark = '✓' | '●' | '○'

function Step({ mark, children }: { mark: Mark; children: React.ReactNode }) {
  const tone = mark === '✓' ? 'text-low' : mark === '●' ? 'text-accent' : 'text-muted'
  return (
    <li className="flex gap-2 text-sm">
      <span aria-hidden="true" className={tone}>
        {mark}
      </span>
      <span className={mark === '○' ? 'text-muted' : ''}>{children}</span>
    </li>
  )
}

interface Props {
  searched: boolean
  routes: UseQueryResult<RoutesResponse, unknown>
  risk: UseQueryResult<RiskResponse, unknown>
  now?: () => number
}

/**
 * What the search is doing right now. Each step is a real finished stage: the routes request
 * and the risk request (weather + scoring happen together on the server).
 */
export function SearchStatus({ searched, routes, risk, now = Date.now }: Props) {
  if (!searched) return null

  const routesFailed = routes.isError
  const riskFailed = !routesFailed && risk.isError
  const loadingRoutes = routes.isPending && !routesFailed
  const loadingRisk = !loadingRoutes && risk.isPending && !routesFailed && !riskFailed
  const checkpoints = routes.data && totalCheckpoints(routes.data.routes, routes.data.interval_mi)

  return (
    <section aria-label="Search progress" className="mt-3 space-y-2">
      {(loadingRoutes || loadingRisk) && (
        <ul aria-live="polite" className="space-y-1">
          <Step mark={loadingRoutes ? '●' : '✓'}>Finding truck routes…</Step>
          <Step mark={loadingRoutes ? '○' : '●'}>
            {checkpoints ? `Checking weather at ${checkpoints} checkpoints…` : 'Checking weather…'}
          </Step>
          <Step mark="○">Scoring risk</Step>
        </ul>
      )}

      {routesFailed && (
        <Problem
          message={friendlyMessage(routes.error)}
          retry={isRetryable(routes.error) ? () => void routes.refetch() : undefined}
        />
      )}

      {riskFailed && (
        <Problem
          message={`${friendlyMessage(risk.error)} The routes are shown, but their weather risk is unknown.`}
          retry={isRetryable(risk.error) ? () => void risk.refetch() : undefined}
        />
      )}

      {risk.data?.stale && risk.data.weather_as_of && (
        <p role="status" className="rounded-md bg-moderate/20 px-3 py-2 text-sm">
          Weather as of {relativeAge(risk.data.weather_as_of, now())}. Live data temporarily
          unavailable.
        </p>
      )}
    </section>
  )
}

function Problem({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-severe/40 bg-severe/5 px-3 py-2 text-sm">
      <p className="text-severe">{message}</p>
      {retry && (
        <button
          type="button"
          onClick={retry}
          className="mt-2 rounded-md border border-line bg-white px-3 py-1 text-sm hover:bg-black/5 focus:ring-2 focus:ring-accent/40 focus:outline-none"
        >
          Try again
        </button>
      )}
    </div>
  )
}
