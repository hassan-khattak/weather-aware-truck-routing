# Weather-Aware Truck Routing

Pick the safest truck route for a trip by looking at the weather the truck will actually meet, when it gets there, for its load weight and its travel time. A React + TypeScript + MapLibre front end on a Django REST back end.

- Search a trip: origin, destination, departure time (in the origin's local time) and cargo weight.
- Get up to three **real truck routes** drawn immediately, then a **risk-coloured** route, a **recommendation with the reason**, and a checkpoint list with the cause of every risk level.
- Explore the **next 48 hours** with a weather overlay (risk for this truck, wind, rain, snow), a slider, a moving truck marker and ▶ Play.

How the problem was read, what was assumed where the spec was ambiguous, and how it scales are in **[PLAN.md](PLAN.md)**. Read that for the *why*; this file is the *how*.

---

## Quick start

You need Docker (with Compose) and `make`.

```bash
git clone https://github.com/hassan-khattak/weather-aware-truck-routing.git
cd weather-aware-truck-routing
cp .env.example .env      # then add your TomTom key (below), or use the keyless demo
make dev-up
```

Open **http://localhost:5173**.

**With a TomTom key** (free at <https://developer.tomtom.com>): put it in `.env` as `TOM_TOM_API_KEY=...`. Search any two US places. Weather comes from Open-Meteo, which needs no key.

**Without a key**, replay the recorded data for the four sample trips:

```bash
PROVIDERS_MODE=fixtures make dev-up
```

then click one of the sample trips (Denver → Cheyenne, Salt Lake City → Denver, Chicago → Dallas, Seattle → Chicago). Fixture mode is for demos and tests only; the server refuses to start in it with `DEBUG` off.

`make dev-down` stops everything. The API documentation is at <http://localhost:5173/api/docs/>.

---

## How it works

```
Browser (React + TypeScript + MapLibre GL)
   │  one HTTPS origin, no CORS
   ▼
CloudFront ──/*──────► S3 (static build)
     └──────/api/*──► EC2: Caddy → Django (DRF)
                                 ├─► TomTom   (truck routing + search)
                                 ├─► Open-Meteo (hourly forecast)
                                 ├─► Towns    (PostGIS + GeoNames, offline)
                                 └─► Cache    (Django cache framework)
                        Postgres + PostGIS
```

- `POST /api/v1/routes` returns the routes in about a second, so the map can draw them straight away.
- `POST /api/v1/risk` returns checkpoints, risk, the recommendation and the 48-hour heatmap (about 12 KB gzipped for the longest sample trip, packed as typed arrays so the slider needs no further network calls).
- All graded logic (risk levels, load rules, miles per level, ranking, checkpoint placement, ETAs with hours-of-service rests) is pure Python in `backend/core/`, with no framework or I/O imports, and every threshold lives in `backend/rules.yaml`.

### The main interpretations (full table in [PLAN.md](PLAN.md#2-reading-the-spec-interpretations-and-assumptions))

| Spec item | What I did |
|---|---|
| Sampling interval | Chosen automatically from the longest route (10, 25 or 50 mi), the same for every route |
| Boundaries such as 0.25 in/hr | The boundary belongs to the higher band, the cautious reading |
| Wind, rain, snow together | The worst of the three; load rules can only raise the level, for wind only, as specified |
| "Fewest Severe miles" | Each mile takes the risk of its closest checkpoint; strict ranking with the trade-off explained on screen |
| ETAs | Truck profile plus US hours-of-service rests (30 min after 8 h of driving, 10 h after 11 h) |
| Unknown weather | Shown as "No forecast", never as safe |
| Time zones | Departure in the origin's local time; every time shown is local to its place, whatever the browser's zone |

---

## Testing

```bash
make test        # backend (pytest) and frontend (vitest)
make test-core   # only the pure domain core
make lint        # ruff, mypy (strict), eslint, tsc, prettier
cd frontend && npm run e2e   # Playwright journeys (needs `uv sync` in backend/ first)
```

- The domain core was written test-first (tests were committed before the code that passes them), with table-driven boundary tests and property-based tests for invariants such as "miles per level add up to the route length" and "load never lowers risk". Coverage on `core/` is gated at 90%.
- Provider adapters are tested against recorded real responses, so CI never needs live services.
- Playwright runs the full journeys against the real API in fixture mode: the sample trips, selecting routes, checkpoint tooltips, slider and Play with no network calls, every error path (forced through a fixture-mode-only header), phone layout, time-zone invariance (browser in Karachi vs New York), and the **production build** (which must load its map worker and log no errors).
- Accessibility is checked with axe in the unit tests and with Lighthouse (100 on the first screen).

CI (GitHub Actions) runs all of this on every push.

---

## Deployment

Infrastructure is defined in Terraform (`infra/`): an EC2 instance with an Elastic IP, S3 + CloudFront (one origin, free HTTPS), IAM, ECR and a billing alarm. The instance accepts traffic only from CloudFront (managed prefix list plus a secret origin header checked by Caddy). Deploys run from GitHub Actions (`.github/workflows/cd.yml`): build the image, wait for **manual approval**, authenticate to AWS with **OIDC** (no stored keys), roll out over SSM, publish the front end, and finish with a smoke test that the live `/api/v1/health` reports the deployed commit. Secrets (TomTom key, Django secret, origin secret) live in SSM Parameter Store, never in git.

Useful targets: `make infra-bootstrap`, `make infra-plan`, `make infra-apply`, `make app-stop`, `make app-start`, `make app-status`.

---

## Known limits

Short list; the full one with reasoning is in [PLAN.md](PLAN.md#9-known-limitations-and-trade-offs).

- Risk between checkpoints is inferred from the nearest checkpoint, so a small storm cell between two can be missed, more so at 50-mile spacing.
- A cold search on a very long trip (~1,000 mi) takes 5–7 s, almost all of it TomTom returning three truck routes; short trips take 1–2 s and repeats are instant.
- About 586 KB gzipped in total (MapLibre is most of it), above my first 500 KB target.
- Typical traffic, not live traffic; continental US only.

## Roadmap

Trip Watch alerts when a forecast changes the recommendation, conservative (gust-based) mode and rain/snow load rules, weather-adjusted speeds, truck-stop-aware rest planning, Canada and Mexico, a lazily loaded map, and Redis plus a job queue when load grows (the scaling path is in [PLAN.md](PLAN.md#5-scalability)).

## Attribution

Weather data by [Open-Meteo](https://open-meteo.com/) (CC BY 4.0) · Routing and search by [TomTom](https://developer.tomtom.com/) · Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, tiles by [OpenFreeMap](https://openfreemap.org/) · Place names from [GeoNames](https://www.geonames.org/) (CC BY 4.0).
