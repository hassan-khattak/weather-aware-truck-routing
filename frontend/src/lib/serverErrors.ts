import { ApiError } from '../api/client'
import type { TripErrors } from './validateTrip'

/** Field messages from a server VALIDATION_ERROR, mapped onto the form's fields. */
export function serverFieldErrors(error: unknown): TripErrors {
  if (!(error instanceof ApiError) || error.code !== 'VALIDATION_ERROR') return {}
  const result: TripErrors = {}
  for (const [path, message] of Object.entries(error.fields)) {
    if (path.startsWith('origin')) result.origin ??= message
    else if (path.startsWith('destination')) result.destination ??= message
    else if (path === 'departure_local') result.departure ??= message
    else if (path === 'load_lb') result.load ??= message
  }
  return result
}

/** Problems worth offering "Try again" for: the user did nothing wrong and it may pass. */
export function isRetryable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    ['NETWORK', 'PROVIDER_UNAVAILABLE', 'RATE_LIMITED'].includes(error.code)
  )
}
