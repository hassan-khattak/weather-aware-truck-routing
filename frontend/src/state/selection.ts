import type { RiskResponse, RoutesResponse } from '../api/types'

/**
 * Which route is selected: the user's choice if it still exists, otherwise the recommended route
 * once risk is known, otherwise the first route (the fastest one TomTom returned).
 */
export function resolveSelectedId(
  userChoice: string | null,
  routes: RoutesResponse | undefined,
  risk: RiskResponse | undefined,
): string | null {
  const ids = routes?.routes.map((r) => r.id) ?? []
  if (userChoice && ids.includes(userChoice)) return userChoice
  const recommended = risk?.recommendation.route_id
  if (recommended && ids.includes(recommended)) return recommended
  return ids[0] ?? null
}
