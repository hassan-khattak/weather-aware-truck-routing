import { QueryClient } from '@tanstack/react-query'

/**
 * `networkMode: 'always'`: by default TanStack Query PAUSES requests while the browser says it is
 * offline, which would leave the progress steps spinning forever. We want the request to run and
 * fail, so the person sees "Can't reach the server" and a Try again button.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false, networkMode: 'always' } },
  })
}
