# Engineering Approach & Design Decisions

**Weather-Aware Truck Routing**: a React + Django app that helps a truck driver pick the safest route based on weather at the truck's arrival time, load weight and travel time.

This document explains *how* I approached the problem: how I read the spec, the assumptions I made where it was ambiguous, the traps I designed around, and how the system is meant to scale. The README covers setup and usage.

---

## 1. How I approached it

I started from the product side before touching any code: who uses this, what decision they're making, and what a wrong answer costs. A truck driver choosing a route in bad weather needs an answer that is **correct, explainable and honest about uncertainty**. That shaped five principles I applied to every decision:

1. **No manual tuning by the user.** The app picks sensible defaults itself (sampling interval, units, time zones).
2. **Simple for the MVP, with a known path to scale.** Every component has a documented next step.
3. **Nothing fake.** No fabricated alternative routes, no simulated progress bars, and unknown weather is never shown as safe.
4. **The spec is the contract.** Where the spec is explicit, I follow it literally. Where it's ambiguous, I pick the safer reading and write it down here.
5. **Correctness and clarity over extra features.**

The brief weights logic and map performance at 40% each, so most of the design effort went there: a pure, test-driven risk engine, and a map that never makes a network call while you explore it.

---

## 2. Reading the spec: interpretations and assumptions

| Spec item | Ambiguity | My decision | Why |
|---|---|---|---|
| "Sample every 10 / 25 / 50 miles" | User-selected? All three? | **Chosen automatically** from the longest route: < 400 mi → 10, 400–1,000 → 25, > 1,000 → 50. **The same interval for all routes.** | No user input needed; denser sampling where it matters most; keeps checkpoints at ≈ 40–56 per route; comparing routes is only fair if risk is measured the same way on each |
| Risk table boundaries | 0.25 in/hr appears under both Moderate and High | **The boundary belongs to the higher band**; the top rain and snow bands follow `>` literally (1.00 in/hr rain = Severe) | The cautious reading for a safety tool, and consistent with "≥ 55 mph" being No Travel |
| Wind, rain, snow per checkpoint | How to combine three conditions | **Worst of the three** | Averaging would hide a single dangerous condition |
| Load rules | Order of application; rain/snow? | Applied after worst-of; **can only raise** the level; **wind only**, as specified | Load mostly affects crosswind/rollover risk. For rain and snow, weight cuts both ways (heavier = longer braking, lighter = jackknife risk), so I didn't invent rules. The engine is config-driven, so they can be added later |
| "Wind" | Sustained or gusts? | **Sustained wind** drives the level; **gusts are shown** alongside | Literal reading of the spec, while surfacing what actually matters for trailers. A "conservative mode" on gusts is one config switch |
| "Fewest Severe *miles*" | Weather is sampled at points | **Each mile takes the risk of its closest checkpoint**; checkpoints always at origin and destination; miles always add up to the route length | The most natural, explainable conversion. Average risk is mile-weighted for the same reason |
| Recommendation order | "No Travel" isn't in the ranking | **No-Travel miles are ranked first**, then the spec's four criteria in **strict** order, then a deterministic tie-break | A literal ranking would let a route with No-Travel miles beat one with Severe miles |
| "Balancing risk and time" | Strict order vs a weighted trade-off | Strict order, **with the trade-off explained** on screen: "0 Severe mi vs 25 on Route A; +18 min" | Defensible for safety, testable against the spec, and transparent to the driver |
| "3 route options" | APIs often return fewer | API alternatives first; generated alternatives **only if** they're real truck routes, < 70% overlapping and ≤ 1.4× the fastest time; otherwise fewer routes with a note | A fake "alternative" that loops for two hours is worse than an honest "2 distinct routes found" |
| ETA "at each checkpoint" | How realistic? | Truck routing profile, 65 mph cap, typical traffic for the departure time, **and US hours-of-service rules** (30-min break after 8h of driving, 10h rest after 11h) | A 16-hour drive really includes a 10-hour stop, so the second half of the trip happens in different weather. Assumption: the driver starts fully rested |
| Departure time | Which time zone? How far ahead? | Entered in the **origin's local time**; allowed from now to +48h | Drivers think in local time; forecasts are reliable for roughly 2–3 days |
| Forecast beyond available data | Unknown weather | Shown as **"No forecast"**, never Low; a note on routes using long-range data | Unknown ≠ safe |
| Heatmap | What does it show? | **Risk for this truck** (same rules, including load) by default, with raw Wind/Rain/Snow layers | Colours mean the same thing everywhere on the map |
| Forecast slider | 0h = now or departure? | **0h = departure**, with a moving truck marker showing where the truck is at that hour | The slider answers "what's the weather around me at this point in my trip?" |
| Load weight | Cargo or gross? | The input is **cargo weight** (used by the load rules, as specified); the routing engine receives cargo + a configurable tare weight | Truck routing restrictions depend on gross weight |
| Coverage | Units and rules are US-specific | **Continental US** for the MVP | mph/inches/pounds and federal hours-of-service rules; Canada/Mexico are on the roadmap |

---

## 3. Subtle problems I designed around

These are the details that look simple but quietly break correctness:

- **Time zones.** A Chicago → Denver trip crosses zones, the forecast API has its own time, and the viewer's browser can be anywhere. The client sends the departure as *origin wall-clock time*; the server resolves the zone from coordinates (offline), computes everything in **UTC**, and every displayed time is local to its place. The results are identical regardless of the viewer's browser time zone, and that's covered by an E2E test.
- **Matching an ETA to a forecast hour.** Precipitation is reported as the total for the hour *ending* at a timestamp, so an arrival at 2:40 PM uses the 3:00 PM value. Wind is instantaneous, so I take the higher of the two surrounding hours.
- **Units and double counting.** "Precipitation" includes snow as water equivalent. Using it for rain counts a snowstorm twice. Rain is `rain + showers`; snow is snowfall depth (what the in/hr thresholds clearly mean). Imperial units are requested directly from the API, and values are rounded on ingest so `0.2499999` can't slip under a boundary.
- **ETAs from averages.** `distance ÷ average speed` ignores city slowdowns. ETAs are interpolated between the routing engine's own timing points along the route, then shifted by the required rest stops.
- **Same road, different risk.** Two routes sharing an interstate can show different risk at the same spot, because the truck arrives at different times. That's correct, and the UI says so.
- **Determinism.** Ties in the ranking are broken by fixed rules, and a property test asserts the recommendation doesn't depend on the order routes arrive in.
- **Heatmap ≠ density.** Map libraries ship a "heatmap" layer that visualises *point density*, which would look right and show the wrong thing. The heatmap here is coloured by risk value.
- **Map projection.** Heatmap images are painted in Web Mercator space, so they don't drift north–south on long corridors.

---

## 4. Architecture

```
Browser (React + TypeScript + MapLibre GL)
   │  one HTTPS origin, no CORS
   ▼
CloudFront ──/*──────► S3 (static build)
     └──────/api/*──► EC2: Caddy → Django (DRF)
                                 ├─► Routing provider  (TomTom: truck routing + search)
                                 ├─► Weather provider  (Open-Meteo: hourly forecast)
                                 ├─► Town lookup       (PostGIS + GeoNames, offline)
                                 └─► Cache             (Django cache framework)
                        Postgres + PostGIS
```

**Key choices:**
- **A pure domain core.** All graded logic (risk classification, load rules, miles attribution, ranking, checkpoint placement, ETAs, hours of service) is plain Python with **no framework or I/O imports** (enforced by a test). External services plug in through small adapters behind interfaces, so a provider can be swapped (for example TomTom → HERE) by writing one adapter.
- **All thresholds in one file.** `rules.yaml` mirrors the spec's tables almost line by line and is validated at startup. Intervals, load rules, quality gates and grid sizes are tunable without code changes.
- **A two-step API.** `POST /routes` returns routes in about a second, so the map draws them immediately. `POST /risk` then returns checkpoints, scores, the recommendation and the 48-hour heatmap. The progress indicator reflects real stages, not an animation.
- **The backend explains itself.** The reasons for each checkpoint's level and the recommendation sentence are generated next to the decision, so the explanation can never disagree with it.
- **Truck routing provider.** I evaluated OpenRouteService first, but its public API limits alternative routes to short distances, which rules it out for multi-state trips. TomTom supports truck mode with vehicle weight, a max-speed parameter, alternatives and historical-traffic ETAs for a future departure.
- **PostGIS, not a vector database.** Nearest-town lookups are a spatial question (distance), not a semantic-similarity one, so PostGIS with a spatial index is the right tool. It also sets up future features like "which saved trips cross this storm?"

---

## 5. Scalability

The expensive part of each search is weather, so that's where the scaling design focuses:

- **Snap to a weather grid.** Every checkpoint and heatmap cell is snapped to a fixed grid (0.1° for checkpoints; 0.2° heatmap cells, growing to 0.4° and 0.8° on longer trips). The forecast models behind the data are roughly 3–13 km resolution, so no real accuracy is lost.
- **One cache entry per grid cell, shared by all users.** Each entry holds the cell's full hourly series, so one fetch serves every hour, every route, the slider and **every user** who passes through that cell within the hour. Trucks drive the same corridors, so **cost and latency drop as usage grows**.
- **Fetch only what's missing, in bulk.** Missing cells are requested in batched multi-location calls, in parallel.
- **Sized for the weather provider's limits.** The free forecast API bills one call per location (600 per minute, 10,000 per day), so heatmap cells get coarser on long trips, keeping any single search to a few hundred locations. Measured on the sample trips: about 60 to 190 corridor cells.
- **Cache sized on purpose.** Django's cache keeps only 300 entries by default and silently culls the rest; one long trip would have evicted every other trip's weather. The limit is raised to 20,000 entries (each entry is a few KB).
- **Stateless API servers.** Any instance can serve any request; state lives in the cache and database.

**Scaling path (in order, none requiring frontend changes):**
1. Move the cache from Postgres to **Redis** (a settings change through Django's cache framework).
2. Move `/risk` computation to a **background job queue** if it becomes CPU-heavy.
3. Run the same containers on **ECS** behind a load balancer, with **RDS** (PostGIS) and **ElastiCache**.
4. Consider a commercial weather plan or a self-hosted forecast API at high volume.

---

## 6. Map and UI performance

Smoothness was treated as a requirement, with explicit rules:
- **Zero network calls while exploring.** All 49 forecast hours arrive once, packed as compact typed arrays (one byte per cell per hour per layer) rather than verbose JSON.
- **Pre-painted heatmap frames.** The 49 hourly images are painted once in the background. Moving the slider swaps one frame, and Play cross-fades between frames so the weather flows.
- **The slider bypasses React re-renders.** The map subscribes to the slider state directly, so dragging doesn't re-render the panel.
- **Layers are created once.** Selecting a route changes styles; nothing is removed or re-added.
- **Simplified geometry for drawing**, full geometry for the maths.
- **A continuous truck marker** driven by a per-route timeline that includes stops.
- **Target: 60 fps** while dragging or playing. CI smoke-tests frame times in headless Chrome (software rendering, so it only catches gross regressions); real-hardware profiling is done by hand.
- **Tested as built.** One Playwright test runs the production bundle (not the dev server) and fails on any console error, because bundling can break things the dev server hides (it once did: the map's worker file was missing from the build, so nothing but the basemap was drawn).

---

## 7. Reliability, security and operations

- **Always-on hosting**, defined in **Terraform** (EC2, Elastic IP, S3, CloudFront, IAM, ECR, billing alarm): no cold starts, and the infrastructure is reproducible.
- **A single origin via CloudFront**: free HTTPS, no CORS, and no mixed-content issues. The EC2 origin only accepts traffic from CloudFront (managed prefix list + a secret origin header).
- **Security headers everywhere:** CloudFront adds a strict Content-Security-Policy (own files, the OpenFreeMap tiles and the map worker only), HSTS, `X-Frame-Options: DENY`, `Referrer-Policy` and `Permissions-Policy`; Django adds `nosniff`, frame and opener policies to API responses. Rate limits count the real client IP through the CloudFront → Caddy chain (`NUM_PROXIES`), and a spoofed `X-Forwarded-For` prefix is ignored.
- **No secrets in the repo or the browser bundle.** The basemap needs no key; routing and weather keys stay on the server; secrets live in SSM Parameter Store.
- **CI/CD with GitHub Actions:** lint, type-checks, unit/integration/E2E tests on every push. Deploys require **manual approval**, authenticate to AWS with **OIDC** (no stored AWS keys), roll out over **SSM** (no SSH from CI), and finish with a smoke test. Images are tagged by commit for easy rollback.
- **Graceful degradation:** if a provider fails, the last cached forecast is served with a clear "weather as of …" label. Rate limiting protects the free API quotas. Every error maps to a plain-language message with a next step.

---

## 8. Testing strategy

- **Test-driven development for the domain core.** Tests were written from the spec's tables first; the commit history shows test commits before implementation commits.
- **Table-driven boundary tests** for every threshold edge (for example `rain = 0.25 → High`, `wind 50 mph + 30,001 lb → No Travel`).
- **Property-based tests** (Hypothesis) for invariants that must always hold: risk miles add up to route distance, load rules never lower risk, heavier loads never lower risk, the recommendation is independent of input order, and ETAs never go backwards.
- **Adapter tests against recorded real API responses**, so CI never depends on live services.
- **A golden end-to-end API scenario** with frozen time.
- **Playwright E2E tests** for the full journey, including **time-zone invariance** across browser zones. They run in a test-only fixture mode that replays recorded responses with timestamps re-based to "now". Every error path is exercised end to end by forcing it through a fixture-mode-only request header (it cannot exist in production), and the same journeys run against the production build.

---

## 9. Known limitations and trade-offs

- **Sampling resolution:** risk between checkpoints is inferred from the nearest checkpoint; a small storm cell between two checkpoints can be missed, more so at 50-mile intervals.
- **Strict ranking:** a route can be recommended despite being considerably longer if it avoids Severe miles. This is intentional for safety and always explained, but a fleet might prefer a tolerance.
- **Rest stops are placed exactly where a driving limit is reached**, not at real truck stops.
- **Typical traffic, not live traffic**, since departures are in the future.
- **Forecast uncertainty** grows with lead time; the app flags long-range checkpoints but doesn't model probabilities.
- **CloudFront → origin traffic is HTTP** in this MVP (locked to CloudFront); a production setup would add TLS to the origin.
- **Cold `/routes` is slow on very long trips.** TomTom itself needs about 5–7 seconds to return three truck routes for a ~1,000-mile trip (a ~2 MB response; one route alone still takes ~2.5 s). Short trips answer in 1–2 seconds, repeats from the cache in under 150 ms, and the progress steps say what is happening meanwhile. `/risk` is fast (under 2 s cold, under 120 ms warm).
- **Bundle size:** about 586 KB gzipped in total (app 414 KB, map worker 158 KB, CSS 15 KB), above the 500 KB I first aimed for. MapLibre GL v6 is most of it; it is cached immutably after the first visit. Splitting the map into a lazily loaded chunk is on the roadmap.
- **Continental US only.**

---

## 10. Roadmap

- **Trip Watch:** save a trip and get alerted when the forecast changes the recommendation (scheduled re-checks as departure approaches).
- **Conservative mode** (classify on gusts) and **rain/snow load rules**, both through configuration.
- **Weather-adjusted speeds**, resolving the ETA ↔ weather dependency iteratively.
- **Truck-stop-aware rest planning.**
- **Canada and Mexico** support.
- **Lazy-load the map** so the form is interactive before MapLibre arrives, and **cache TomTom routes** per lane and departure hour.
- **Uniform fine-grained sampling** (always 10 mi internally, aggregated for display).

---

## Data attribution
Weather data by [Open-Meteo](https://open-meteo.com/) (CC BY 4.0) · Routing and search by TomTom · Map data © OpenStreetMap contributors, tiles by OpenFreeMap · Place names from GeoNames (CC BY 4.0).