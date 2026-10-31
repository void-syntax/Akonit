# Signal Radar

> You decide what to watch. Signal Radar watches it 24/7.

Condition-driven monitoring of the open internet. You define conditions, the
system collects from many free public sources, detects **early signals** (not
news), and notifies you on your phone.

**Free public sources by default. No LLM or proxies. Optional official APIs can improve coverage; paid reads are capped and off until you add your own credentials.**

---

## Run it locally

**Double-click `start.bat`.** On first run it creates a Python environment,
installs the pinned backend and dashboard packages, and copies safe defaults to
`backend/.env`. Later starts reuse those packages and your settings.

It checks what is installed, creates what is missing, starts everything, waits
until the app actually answers, and opens <http://localhost:3000> in your
browser. The first run takes a few minutes; later ones take seconds.

You need one of these two setups:

| | |
|---|---|
| **Python 3.11+ and Node.js 20+** — `start.bat` prepares and launches the local API, worker and dashboard. |
| **Docker Desktop** — optional; copy `.env.example` to `.env`, then use `docker compose up --build` to run the container stack. |

Nothing else. No account, no API key, no signup, no cloud service.

Not sure what you have? Run **`doctor.bat`** — it lists exactly what is missing
and whether the app is already running.

To stop it: **`stop.bat`**, or close the windows `start.bat` opened.

### The three files

| File | What it does |
|---|---|
| `start.bat` | Starts everything and opens the browser |
| `stop.bat` | Stops it |
| `doctor.bat` | Reports whether this machine is ready |

### What you should see

The worker checks for due sources every 60 seconds and runs one initial collection
on startup. Each source has its own collection interval and may be unavailable
or rate limited, so the first signal can take longer than a minute. Source health
in the dashboard shows which collectors are currently returning data.

Verify the engine itself, with no Docker and no server:

```bash
cd backend
python -m tools.collect_once
```

A healthy run ends with `OK: N signals in the feed`. Run it twice with `--keep`
and the second run reports `signals_with_measured_growth` above zero, which is
how you know the trend detection works and not just the fetching:

```bash
python -m tools.collect_once --keep   # first cycle: creates signals
python -m tools.collect_once --keep   # second cycle: measures growth
```

On the first cycle growth is legitimately zero everywhere: there is no previous
measurement to compare against. That is deliberate — the engine reports nothing
rather than inventing a 100% increase.

### Other checks

```bash
cd backend
python -m pytest                  # unit tests
python -m tools.audit_endpoints   # every endpoint the UI depends on
python -m tools.check_env         # env vars vs Settings, migrations vs models
python -m tools.list_routes       # every route, flags duplicate handlers
```

### Starting it by hand

```bash
docker compose up          # then open http://localhost:3000
```

Without Docker, create the backend environment and install its packages first:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal start the collector with
`.venv\Scripts\python -m app.workers.schedule` from `backend/`, then start the
dashboard with `npm ci` and `npm run dev` from `frontend/`.

## Local data and optional credentials

The default installation needs no keys or accounts. Optional source credentials
and push settings belong in your local `backend/.env`; never commit that file.
For official X post search, add your X API Bearer Token there. X post reads are
pay-per-use; Signal Radar requests at most 10 posts per search and caps reads at
100/day by default. It polls that paid endpoint every three hours to preserve
day-long coverage; the separate public trend feed remains more frequent. At the
currently listed $0.005 per returned post, the hard cap is about $0.50/day;
verify current rates and prepaid credits in X's
Developer Console before enabling it. Set `X_POSTS_DAILY_READ_LIMIT=0` to keep
official X post search disabled. X trends from the public trend feed remain
available without a token.

Official Reddit OAuth also uses credentials from your own approved Reddit app
(`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`). The collector rotates through
communities and falls back to public RSS/archive sources when OAuth is not
configured. External app access requires Reddit approval and compliance with its
Data API terms; register your app under Reddit's current developer process. Set
`REDDIT_USER_AGENT` to the app name and your actual Reddit username/contact.
TikTok's broad Research API access is restricted to eligible, approved
researchers. Public tag pages may challenge automated requests, so this app does
not retry them or bypass the challenge. Without approved Creative Center access,
the TikTok trends collector stays in an optional-credentials state. The app
cannot see all TikTok posts or private data.
Approved applicants can also apply for TikTok's Commercial Content API; its
creator-country filter currently covers EEA countries, excluding the UK and
Switzerland. Add the approved
`TIKTOK_COMMERCIAL_CLIENT_KEY` and `TIKTOK_COMMERCIAL_CLIENT_SECRET` to enable
this separate branded-content signal source.
The root `.env` is only for Docker Compose. Local database files, logs, caches,
and generated signal digests are ignored by Git and remain on your computer.

### Add more public sources

Put comma-separated RSS or Atom URLs in `EXTRA_RSS_FEEDS` in your local
`backend/.env`. The collector accepts up to ten HTTP(S) feeds and bounds each
response to 2 MB. If a site has no feed, you can run RSS-Bridge yourself and add
its feed URL; public shared bridge instances may disappear or rate-limit you.
Bluesky is sampled from its public Jetstream WebSocket in short bounded windows.
Mastodon instances are configurable through `MASTODON_INSTANCES` (up to six);
public timelines and search depend on each server's configuration and do not
amount to global federation search.

The default ports are bound to `127.0.0.1`. Authentication is disabled for a
single-user local installation; do not expose the app directly to the internet.

## License

Signal Radar is distributed under the [MIT License](LICENSE).

### There is no login

`AUTH_DISABLED` defaults to `true`, so the API creates one local account on the
first request and uses it for everything. Radars, saved signals and
notifications work immediately, with no token, cookie or OAuth anywhere in the
flow. Set `AUTH_DISABLED=false` only if you put this behind a shared host.

### The engine searches what you asked for

Collection is tag-driven rather than fixed. The keywords inside your custom tags
and your radar's `KEYWORD` conditions become the queries the collectors actually
run, and the countries come from your radars (falling back to your profile
defaults, then to a built-in list). A radar for "Korea + Makeup" makes the
collectors fetch Korean makeup content instead of whatever seed happened to be
hardcoded in the adapter.

### Why local is the primary target

The product's whole value is noticing something *early*, so the collection
interval is 60 seconds. That needs a long-lived process on a machine you control.
A hosted cron cannot keep that cadence reliably, and this build has no hosted
deploy path at all: no Supabase, no Vercel, no GitHub Actions workflow. It is a
tool you run, not a service you sign up for.

`.github/workflows/collect.yml` still exists for people who want a hosted
collector, but it is no longer the recommended path.

---

## Architecture

```
COLLECTORS            public-source adapters, optional credentials, self-healing
      ↓
NORMALIZATION         text/URL/hashtag normalization, country resolution
      ↓
DEDUPLICATION         canonical URL + 64-bit simhash, conservative merging
      ↓
SIGNAL DETECTION      growth · acceleration · recency · persistence ·
                      cross-source → strength 0-100, lifecycle
                      NEW → RISING → BREAKOUT → FADING
      ↓
SIGNAL DATABASE       signals + append-only signal_snapshots history
      ↓
RADAR CONDITION ENGINE  AND / OR / NOT / EXCLUDE over 9 condition types
      ↓
USER FILTER           saved · ignored · threshold
      ↓
NOTIFICATION ENGINE   OFF · INSTANT · 15-MIN · HOURLY · DAILY DIGEST
      ↓
WEB APP / PUSH / TELEGRAM   Next.js + SSE, web push (VAPID), Telegram bot
```

Each layer is independent and replaceable. A failing collector never stops
the pipeline.

---

## Sources

Priority is social and viral content first, then trend/search, then AI/tech.
The collector registry covers many public feeds and APIs. A registered adapter
does not mean the platform grants complete access: check per-source health,
credentials, rate limits, and each platform's current access terms.

| # | Source | Strategy | Credentials | Status |
|---|--------|----------|--------------|--------|
| 1 | **TikTok** | public tag pages; approved Commercial Content API adds disclosed branded content | optional approval | limited public data |
| 2 | **Bluesky Live** | short samples from public Jetstream WebSocket | none | live posts; bounded windows |
| 3 | **Bluesky Search** | public AppView search | none | query-dependent |
| 4 | **Mastodon** | public trends/statuses from up to 6 configured instances | none | instance-dependent |
| 5 | **Reddit** | approved OAuth → public archive/RSS fallbacks | optional approved app | limited by instance/rate limits |
| 6 | **X Trends** | public trend cards | none | third-party aggregate |
| 7 | **X Posts** | official recent-post search, every 3h | Bearer token + credits | capped at 100 returned posts/day |
| 8 | **Custom RSS / Atom** | user-configured feeds; up to 10 | none | depends on supplied feeds |
| 9 | **YouTube** | channel RSS/public pages; Data API when configured | optional API key | route-dependent |
| 10 | **Google Trends / News** | public trend feeds/search | none | public datasets |
| 11 | **GitHub / Hugging Face** | public API/search and trending | optional tokens | public project signals |
| 12 | **Product Hunt / HN / npm / DEV / Lobsters / Stack Overflow** | public APIs and RSS | mostly none | source-specific limits |
| 13 | **Other registered adapters** | arXiv, SEC, patents, trademarks, Polymarket, etc. | source-specific | see source health |
### Why Instagram is marked honestly

Public hashtag pages load their data through an **authenticated internal
GraphQL call** (verified: `media_count`, `edge_hashtag_to_media`,
`follower_count` are all absent from the served HTML). Reading it would mean
circumventing an access control, so we do not. The adapter is fully
implemented against the official Graph API and activates automatically when a
token is present. Beauty/fashion signals are covered meanwhile by TikTok,
YouTube, X and Google Trends.

We never bypass CAPTCHA, logins, paywalls, rate limits or anti-bot systems.

### Credential cascade

Adapters declare an ordered list of strategies. The runner tries each until one
produces data. Optional credentials activate the official API path where one is
available; they do not bypass platform approval or usage limits.

---

## Detection

```
strength = growth + acceleration + recency + absolute
         + persistence + cross-source confirmation   (weights in settings)
```

All weights and thresholds live in `app/core/config.py`; nothing is hardcoded
in the engine.

**POPULAR ≠ RISING.** A large flat object is penalised by `staleness_penalty`;
a small object with sharp acceleration scores higher. This is enforced by a
test (`test_popular_but_flat_scores_lower_than_sharp_rise`).

Snapshots are append-only, so growth, acceleration, lifecycle and charts are
all derived from real history.

### Freshness is enforced at ingestion

A signal only enters the feed if it was published within
`detect_max_age_hours` (72 by default). This matters more than it sounds:
search-driven collectors keep returning the same evergreen hits, and without a
publication-date cutoff a five-year-old video enters the feed looking like a
breaking trend.

The feed's honesty depends on three rules that were bugs once:

* **No baseline, no growth.** A first sighting has nothing to compare against,
  so growth is `0`, not `100`. Treating "appeared" as "surged" filled the feed
  with identical RISING items.
* **Unknown age stays unknown.** Feeds that expose no count (TikTok tag pages,
  X trends24, Reddit PullPush) cannot fake momentum, and undated YouTube Shorts
  are dropped rather than assumed fresh.
* **Publication date, not discovery date.** `first_seen_at` is the date the
  thing was published, so age means what a reader thinks it means.

YouTube's real trending feed (`/feed/trending`) renders an anonymous
`feedNudgeRenderer` with zero videos, so it cannot be used. The adapter falls
back to public search and now filters on the publication date it can actually
parse — the old relative-time pattern required whitespace and YouTube writes
`8mo ago` without any, so every video used to come back undated.

---

## Quick start

### Locally, no Docker (SQLite)

```bash
cd backend
pip install -r requirements-dev.txt
cp ../.env.example .env          # DATABASE_URL defaults to SQLite
uvicorn app.main:app --reload          # API on :8000
python -m app.workers.schedule         # 24/7 worker, separate process
```

```bash
cd frontend
npm install
npm run dev                            # web on :3000
```

### With Docker (Postgres + Redis)

```bash
cp .env.example .env
docker compose up --build
```

This starts five services: `db`, `redis`, `api`, `worker` and `web`. The worker
runs the pipeline on a schedule; see [Staying live 24/7](#staying-live-247).

---

## Staying live 24/7

There are two ways to keep the radar collecting, and they are not
interchangeable.

### Option A — long-running worker (self-hosted)

`python -m app.workers.schedule` runs forever and is what `docker compose`
starts for you. It schedules four jobs:

| Job | Default interval | What it does |
|-----|------------------|--------------|
| `collect` | `COLLECT_INTERVAL_SECONDS` (900) | fetch → normalize → dedup → detect |
| `match` | 5 min | evaluate signals against every radar |
| `notify` | 1 min | queue and deliver due notifications |
| `metrics` | `SNAPSHOT_INTERVAL_SECONDS` (900) | recompute growth/strength from snapshots |

Graceful shutdown on SIGTERM/SIGINT, `max_instances=1` so a slow tick is never
overlapped, and `coalesce=True` so missed ticks do not pile up.

### Option B — cron runs (serverless / no machine)

When you cannot keep a process alive — your laptop is off, or you deploy to a
platform without a worker — GitHub Actions runs one finite cycle instead.
`.github/workflows/collect.yml` does this on a 20-minute cron:

```bash
python -m tools.seed_reference     # idempotent
python -m tools.collect_once       # one collect pass, prints JSON
python -m tools.notify_once        # match radars + deliver notifications
```

Each tool is a one-shot command designed to exit, which is exactly what a cron
runner needs. Both write a JSON summary so failures are visible in the run log.

> **Honest limitation:** Option A only runs while the machine is on. Option B is
> the only one that collects while nothing of yours is switched on.

### Database migrations

Schema changes go through Alembic. SQLite databases created before the
product-settings fields are upgraded in place by `app/db/migrate.py` on startup.

```bash
cd backend
alembic upgrade head        # apply
alembic revision --autogenerate -m "describe change"
```

---

## Continuous integration

Two workflows run from this repository.

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `test.yml` | push, pull request | backend tests against Postgres, `alembic check`, `tsc`, `next build` |
| `collect.yml` | cron every 20 min | migrations, seed, one collect cycle, radar matching, notifications |

To let `collect.yml` run, add these repository secrets under
**Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
|--------|----------|---------|
| `DATABASE_URL` | yes | `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB` |
| `SECRET_KEY` | yes | JWT signing |
| `GITHUB_TOKEN` | no | raises the GitHub limit 60 → 5000 req/h |
| `HF_TOKEN` | no | private Hub models |
| `TELEGRAM_BOT_TOKEN` | no | Optional shared bot for legacy deployments; users can connect their own bot in Settings |
| `TELEGRAM_TOKEN_ENCRYPTION_KEY` | required for per-user Telegram bots | Fernet key used to encrypt user bot tokens in the database. `start.bat` creates a local key automatically. |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` | no | web push |

`collect.yml` can also be triggered by hand (**Run workflow**) with a
`full` toggle for collect-only runs.

### Using Supabase as the database

Create the schema once, then point `DATABASE_URL` at it:

```bash
cd backend
python -m tools.dump_schema        # prints the full Postgres DDL
alembic upgrade head               # or apply the DDL directly
```

Row Level Security should stay **enabled** on every table: the application
connects over PostgreSQL directly, while the anon/authenticated PostgREST roles
must not be able to read the data.

The schema predates Alembic, so `alembic_version` may be missing while the
tables already exist. Both `collect.yml` and `tools/_bootstrap.py` detect that and
stamp the baseline before upgrading; a bare `alembic upgrade head` against such a
database would fail on `CREATE TABLE`.

---

## Deployment topology

| Piece | Where it runs |
|-------|---------------|
| Collection, detection, matching, retention | Python in GitHub Actions (`collect.yml`) |
| Read API | Supabase Edge Function `api` (Deno) |
| Web UI | Vercel (Next.js, `frontend/` as root directory) |

The edge function answers from `SUPABASE_DB_URL`, which the platform injects
automatically; `DB_PASSWORD` is only a fallback for local `functions serve`.

### Vercel

One environment variable is required, and it is inlined at build time — without
it the UI silently falls back to `http://localhost:8000`:

```
NEXT_PUBLIC_API_URL = https://<project-ref>.supabase.co/functions/v1/api
```

The client appends `/api/v1` itself, and the edge router strips stacked gateway
prefixes, so no other path configuration is needed. The API is cross-origin in
production, which is why the client never sends `credentials: "include"`: a
credentialed request to a wildcard `Access-Control-Allow-Origin` is rejected by
the browser.

---

## Radars

A radar is a condition tree:

```json
{
  "op": "AND",
  "children": [
    { "op": "OR",  "children": [
        { "type": "country", "operator": "IN", "value": ["KR", "JP"] } ] },
    { "op": "OR",  "children": [
        { "type": "source", "operator": "IN",
          "value": ["tiktok", "youtube"] } ] },
    { "op": "NOT", "children": [
        { "type": "tag", "operator": "IN", "value": ["cosplay"] } ] },
    { "type": "growth", "operator": "GT", "value": 100 }
  ]
}
```

Condition types: country · source · tag · keyword · growth · activity · age ·
status · strength. Operators: IN, NOT_IN, GT, GTE, LT, LTE, EQ.

The UI builder is visual — no SQL, no code.

---

## Custom tags

Users create their own tags with keywords, hashtags, countries, sources and
excludes. Matching is deterministic (no LLM): normalization → exact hashtag →
alias phrase → keyword phrase → token-set fuzzy. The `TagMatcher` interface
leaves room for an embeddings implementation later.

---

## Environment

All optional. With an empty `.env` the system already runs on free public data.

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | raises GitHub limit 60 → 5000 req/h |
| `HF_TOKEN` | private Hub models/spaces |
| `YOUTUBE_API_KEY` | unlocks Data API v3 (quota-aware) |
| `TIKTOK_API_TOKEN` | unlocks official Creative Center API |
| `INSTAGRAM_ACCESS_TOKEN` + `META_APP_ID` | unlocks Instagram |
| `TELEGRAM_BOT_TOKEN` | optional shared Telegram bot; each local user can also connect a private bot in Settings |
| `TELEGRAM_TOKEN_ENCRYPTION_KEY` | encrypts personal bot tokens stored in the database; keep it private and persistent |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | enables web push |
| `REDIS_URL` | pub/sub; falls back to an in-memory bus |

---

## Project layout

```
backend/
  app/
    core/          config, security, logging
    db/            session, redis bus
    models/        20 SQLAlchemy entities
    pipeline/
      collectors/  15 adapters + registry + http client
      normalization/ dedup/ detection/ matching/
    radar/         condition AST + evaluator
    notifications/ dispatcher, telegram, webpush, formatter
    services/      pipeline orchestrator, radar service
    workers/       24/7 scheduler + tasks
    api/v1/        auth, taxonomy, radars, signals, stream, system
  tools/           verification scripts
  tests/           27 unit tests
frontend/
  src/app/         feed, login, radars, saved, profile, settings, signal detail
  src/components/  SignalCard, ConditionBuilder, AppShell
  src/lib/         api client, SSE hook, formatters
```

---

## Non-goals (by design)

- No LLM / no AI API anywhere — detection is deterministic.
- No maps or geographic visualisation — countries are badges only.
- No scraping-service dependency or proxy requirement. Optional official APIs
  may cost money; the X reads budget is capped locally.
- Signals are never deleted after a decline; history is always kept.
cd frontend
npm install
npm run dev
```

### Verification tools (real data, no mocks)

```bash
cd backend
python -m tools.probe_sources      # every collector against the live internet
python -m tools.e2e_check          # full pipeline: fetch → signal → radar → notify
python -m tools.check_api          # every HTTP route
python -m tools.check_radar        # condition engine truth table
python -m tools.live_check         # end-to-end against running servers
python -m pytest tests -q          # 27 unit tests
```
| 1 | **TikTok** | public tag pages; approved Commercial Content API adds European branded content | approved client key/secret | limited public data |
| 2 | **YouTube** | channel RSS / public page data; Data API v3 when configured | optional API key | depends on configured route |
| 3 | **Reddit** | approved OAuth → public archive and RSS fallback | optional approved app | fallback works without OAuth |
| 4 | **X Trends** | public trend cards | none | external trend feed |
| 5 | **X Posts** | official recent-post search using radar keywords | Bearer Token + prepaid credits | disabled until token; max 100 reads/day |
| 5 | **Google Trends** | Trending Now RSS per country (`approx_traffic`) | none | ACTIVE |
| 6 | **Google News Trends** | `when:1h/6h/24h` recency operator | none | ACTIVE |
| 7 | **GitHub** | search/repositories (new + fast star growth) | optional token | ACTIVE |
| 8 | **Hugging Face** | Hub API (models/spaces/datasets, trendingScore) | optional token | ACTIVE |
| 9 | **Product Hunt** | RSS feed | none | ACTIVE |
| 10 | **Hacker News** | Firebase API | none | ACTIVE |
| 11 | **npm** | registry search (monthly downloads) | none | ACTIVE |
| 12 | **DEV** | articles API | none | ACTIVE |
| 13 | **Lobsters** | RSS | none | ACTIVE |
| 14 | **Stack Overflow** | API 2.3 | none | ACTIVE |
| 15 | **Instagram** | official Meta Graph API | **required** | `⚪ OPTIONAL_CREDENTIALS` |
