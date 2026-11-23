import { useId, useState } from 'react'
import { friendlyMessage } from '../api/client'
import { MIN_PLACE_CHARS, usePlaces } from '../api/hooks'
import type { Place } from '../api/types'
import { useDebounced } from '../lib/useDebounced'

export const AUTOCOMPLETE_DEBOUNCE_MS = 250

interface Props {
  label: string
  value: Place | null
  onChange: (place: Place | null) => void
  error?: string
}

/** Place search box (ARIA combobox). A place only counts once it has been chosen from the list,
 *  so the server always receives exact coordinates. */
export function PlaceField({ label, value, onChange, error }: Props) {
  const id = useId()
  const listId = `${id}-list`
  const [text, setText] = useState(value?.label ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)

  // Follow outside changes (swap button, sample trips): when the chosen place changes, show it.
  const [previous, setPrevious] = useState(value)
  if (value !== previous) {
    setPrevious(value)
    if (value) setText(value.label)
  }

  const debounced = useDebounced(text, AUTOCOMPLETE_DEBOUNCE_MS)
  const searching = open && value === null && debounced.trim().length >= MIN_PLACE_CHARS
  const {
    data: options = [],
    isFetching,
    isError,
    error: lookupError,
  } = usePlaces(searching ? debounced : '')
  const lookupFailed = searching && isError
  const showList = searching && !isError

  function choose(place: Place) {
    setText(place.label)
    setOpen(false)
    setActive(-1)
    onChange(place)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && options.length > 0) {
      event.preventDefault()
      setOpen(true)
      setActive((i) => (i + 1) % options.length)
    } else if (event.key === 'ArrowUp' && options.length > 0) {
      event.preventDefault()
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1))
    } else if (event.key === 'Enter' && showList && active >= 0 && options[active]) {
      event.preventDefault()
      choose(options[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
      setActive(-1)
    }
  }

  const status = lookupFailed
    ? friendlyMessage(lookupError)
    : !showList
      ? ''
      : isFetching
        ? 'Searching…'
        : options.length === 0
          ? 'No matches. Try a nearby city or a ZIP code.'
          : `${options.length} suggestion${options.length === 1 ? '' : 's'}`

  return (
    <div className="relative">
      <label htmlFor={`${id}-input`} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      <input
        id={`${id}-input`}
        type="text"
        role="combobox"
        aria-expanded={showList && options.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        autoComplete="off"
        placeholder="City, address or ZIP"
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          setOpen(true)
          setActive(-1)
          if (value !== null) {
            onChange(null) // editing the text un-chooses the place
          }
        }}
        onKeyDown={onKeyDown}
        onBlur={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        className="w-full rounded-md border border-line px-3 py-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/30 aria-[invalid=true]:border-severe"
      />
      <ul
        id={listId}
        role="listbox"
        aria-label={`${label} suggestions`}
        hidden={!showList || options.length === 0}
        className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-line bg-white shadow-lg"
      >
        {options.map((place, index) => (
          <li
            key={`${place.label}-${place.lat}-${place.lon}`}
            id={`${id}-opt-${index}`}
            role="option"
            aria-selected={index === active}
            // mousedown (not click) so the input keeps focus and blur does not close the list first
            onMouseDown={(event) => {
              event.preventDefault()
              choose(place)
            }}
            className={`cursor-pointer px-3 py-2 text-sm ${index === active ? 'bg-accent/10' : ''}`}
          >
            {place.label}
          </li>
        ))}
      </ul>
      {/* One live region: read out for screen readers, and shown when there is nothing to pick. */}
      <p
        role="status"
        className={
          lookupFailed
            ? 'mt-1 text-xs text-severe'
            : options.length === 0 && showList
              ? 'mt-1 text-xs text-muted'
              : 'sr-only'
        }
      >
        {status}
      </p>
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1 text-xs text-severe">
          {error}
        </p>
      )}
    </div>
  )
}
