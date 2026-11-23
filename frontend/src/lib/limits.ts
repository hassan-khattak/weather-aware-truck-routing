/** Input limits. The backend enforces the real ones from rules.yaml; keep these in sync so the form
 *  can say the same thing before a request is sent. */
export const LOAD_MIN_LB = 1000
export const LOAD_MAX_LB = 80000
export const LOAD_WARNING_LB = 45000
export const DEPARTURE_PAST_GRACE_MIN = 5
export const DEPARTURE_MAX_AHEAD_H = 48
export const MIN_TRIP_SEPARATION_MI = 0.5

export const LOAD_WARNING_TEXT =
  'Exceeds typical legal cargo for a 5-axle tractor-trailer; truck routes may be restricted.'
export const COVERAGE_MESSAGE = 'Currently supports routes within the continental US.'
