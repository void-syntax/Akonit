# Signal Radar

> You decide what to watch. Signal Radar watches it 24/7.

Condition-driven monitoring of the open internet. You define conditions, the
system collects from many free public sources, detects **early signals** (not
news), and notifies you on your phone.

**Zero API cost. No LLM. No scraping services. No proxies. No login walls.**

---

## Architecture

```
COLLECTORS            15 adapters, credential cascade, self-healing
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
Every adapter below was verified against the live site.

| # | Source | Strategy | Credentials | Status |
|---|--------|----------|--------------|--------|
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
produces data. Tokens are **optional** — if one is present in `.env` the better
strategy is used automatically, otherwise the free one runs.

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
| `TELEGRAM_BOT_TOKEN` | no | Telegram notifications |
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
| `TELEGRAM_BOT_TOKEN` | enables Telegram notifications |
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
- No paid APIs, scraping services, proxies or trend aggregators.
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
| 1 | **TikTok** | public tag pages (`__UNIVERSAL_DATA_FOR_REHYDRATION__`) → official Creative Center API | optional | ACTIVE |
| 2 | **YouTube** | search results (`ytInitialData`, incl. Shorts) → channel RSS → Data API v3 | optional | ACTIVE |
| 3 | **Reddit** | PullPush archive → search RSS → official OAuth | optional | ACTIVE |
| 4 | **X / Twitter** | trends24 public trend cards (1h/6h/24h windows) → official API | optional | ACTIVE |
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