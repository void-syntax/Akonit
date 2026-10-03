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

### With Docker

```bash
cp .env.example .env
docker compose up --build
```

- web: http://localhost:3000
- api docs: http://localhost:8000/docs
- worker + beat run automatically

### Without Docker

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # DATABASE_URL defaults to SQLite
uvicorn app.main:app --reload          # API
python -m app.workers.schedule         # 24/7 worker
```

```bash
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