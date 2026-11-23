import type { Place, RiskResponse, RoutesRequest, RoutesResponse } from './types'

const BASE = '/api/v1'

/** Every failure, whether from the server or the network, becomes one of these. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string>

  constructor(status: number, code: string, message: string, fields: Record<string, string> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

const NETWORK_MESSAGE = "Can't reach the server. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again in a minute.'

interface ErrorBody {
  error?: { code?: string; message?: string; fields?: Record<string, string> }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, init)
  } catch (cause) {
    if ((cause as { name?: string } | null)?.name === 'AbortError') throw cause
    throw new ApiError(0, 'NETWORK', NETWORK_MESSAGE)
  }

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Not JSON (for example an HTML error page from a proxy); handled below.
  }

  if (!response.ok) {
    const error = (body as ErrorBody | null)?.error
    if (error?.code && error.message) {
      throw new ApiError(response.status, error.code, error.message, error.fields ?? {})
    }
    throw new ApiError(response.status, `HTTP_${response.status}`, GENERIC_MESSAGE)
  }
  if (body === null) throw new ApiError(response.status, 'BAD_RESPONSE', GENERIC_MESSAGE)
  return body as T
}

export function fetchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  return request<Place[]>(`/places?q=${encodeURIComponent(query)}`, { signal })
}

export function postRoutes(body: RoutesRequest, signal?: AbortSignal): Promise<RoutesResponse> {
  return request<RoutesResponse>('/routes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

export function postRisk(tripId: string, signal?: AbortSignal): Promise<RiskResponse> {
  return request<RiskResponse>('/risk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trip_id: tripId }),
    signal,
  })
}

/** The message to show the user for any error. */
export function friendlyMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : GENERIC_MESSAGE
}
