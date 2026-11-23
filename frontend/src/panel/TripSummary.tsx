import type { RoutesRequest } from '../api/types'
import { summaryTime } from '../lib/time'

const city = (label: string) => label.split(',')[0]

/** The form folded into one line after a search: "Dallas → Denver · Tue 3 PM CST · 42,000 lb ✎". */
export function TripSummary({
  request,
  tz,
  onEdit,
}: {
  request: RoutesRequest
  tz: string
  onEdit: () => void
}) {
  const text = [
    `${city(request.origin.label)} → ${city(request.destination.label)}`,
    summaryTime(request.departure_local, tz),
    `${request.load_lb.toLocaleString('en-US')} lb`,
  ].join(' · ')
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-line bg-black/[0.03] px-3 py-2">
      <p className="text-sm font-medium">{text}</p>
      <button
        type="button"
        onClick={onEdit}
        aria-label="Edit trip"
        className="rounded px-2 py-1 text-base hover:bg-black/10 focus:ring-2 focus:ring-accent/40 focus:outline-none"
      >
        ✎
      </button>
    </div>
  )
}
