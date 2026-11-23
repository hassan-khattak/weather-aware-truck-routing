import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, fetchPlaces, postRisk, postRoutes } from './client'
import type { RoutesRequest, RoutesResponse } from './types'

export const MIN_PLACE_CHARS = 3
const DAY_MS = 24 * 60 * 60 * 1000

/** Retry once for outages the user cannot fix; never for rejected requests. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false
  return (
    error instanceof ApiError && (error.code === 'NETWORK' || error.code === 'PROVIDER_UNAVAILABLE')
  )
}

/** Autocomplete suggestions. Only runs for a query of at least 3 characters. */
export function usePlaces(query: string) {
  const text = query.trim()
  return useQuery({
    queryKey: ['places', text.toLowerCase()],
    queryFn: ({ signal }) => fetchPlaces(text, signal),
    enabled: text.length >= MIN_PLACE_CHARS,
    staleTime: DAY_MS,
    placeholderData: keepPreviousData,
    retry: shouldRetry,
  })
}

/**
 * The two-step search: routes first (the map draws them straight away), then risk.
 * `request` is null until the user submits; `searchId` changes on every explicit submit, so
 * searching again always asks the server afresh. If the stored trip has expired (TRIP_EXPIRED)
 * the routes are fetched again and the risk call repeated, without the user noticing.
 */
export function useTrip(request: RoutesRequest | null, searchId: number) {
  const client = useQueryClient()

  const routes = useQuery({
    queryKey: ['routes', searchId],
    queryFn: ({ signal }) => postRoutes(request as RoutesRequest, signal),
    enabled: request !== null,
    staleTime: Infinity,
    retry: shouldRetry,
  })

  const tripId = routes.data?.trip_id
  const risk = useQuery({
    queryKey: ['risk', searchId],
    queryFn: async ({ signal }) => {
      try {
        return await postRisk(tripId as string, signal)
      } catch (error) {
        if (!(error instanceof ApiError) || error.code !== 'TRIP_EXPIRED') throw error
        const fresh: RoutesResponse = await postRoutes(request as RoutesRequest, signal)
        client.setQueryData(['routes', searchId], fresh)
        return postRisk(fresh.trip_id, signal)
      }
    },
    enabled: tripId !== undefined,
    staleTime: Infinity,
    retry: shouldRetry,
  })

  return { routes, risk }
}
