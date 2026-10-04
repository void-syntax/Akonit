/**
 * Signal Radar read API, stage 1: public endpoints.
 *
 * Everything here is safe to expose without a token: the feed, discovery,
 * signal detail, taxonomy and health. Authenticated routes land in stage 2 and
 * 3; the collector and detector still run from GitHub Actions.
 */

import { one, rows } from "./_lib/db.ts";
import { CONDITION_TYPES } from "./condition_types.ts";
import {
  fail,
  floatParam,
  intParam,
  json,
  listParam,
  params,
  preflight,
  segments,
} from "./http.ts";
import {
  serializeCountry,
  serializeSignal,
  serializeSnapshot,
  serializeSource,
  serializeTag,
} from "./_lib/serialize.ts";

const SIGNAL_COLUMNS = `
  id, title, description, category, hashtags, country_code, country_name, flag,
  source_id, source_url, thumbnail, cross_source_count, first_seen_at,
  last_seen_at, current_activity, previous_activity, growth, acceleration,
  status, strength, age_minutes, activity_metric, keywords, velocity,
  density_count
`;

const ACTIVE = "NEW, RISING, BREAKOUT";

/**
 * Prefix segments that may sit in front of the real route.
 *
 * The Supabase gateway forwards `/functions/v1/<slug>/<rest>` to the function
 * as `/<slug>/<rest>`, and the frontend appends `/api/v1` to its configured
 * base URL. Both can stack, so strip repeatedly rather than once.
 */
const PREFIXES = new Set(["functions", "v1", "api"]);

function stripPrefix(seg: string[]): string[] {
  let out = seg;
  while (out.length > 0 && PREFIXES.has(out[0])) out = out.slice(1);
  return out;
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method === "OPTIONS") return preflight();

  const url = new URL(request.url);
  const path = segments(url);
  const p = params(url);

  try {
    return await route(url, path, p);
  } catch (error) {
    console.error("api error", error);
    return fail(
      error instanceof Error ? error.message : "internal error",
      500,
    );
  }
});

async function route(
  url: URL,
  path: string[],
  p: Record<string, string>,
): Promise<Response> {
  const seg = stripPrefix(path);

  if (seg.length === 0 || seg[0] === "health") {
    return json({ ok: true, service: "signal-radar-api" });
  }

  switch (seg[0]) {
    case "stats":
      return json(await stats());
    case "signals":
      return await signals(url, seg, p);
    case "discover":
      return await discover(p);
    case "countries":
      return json(await countries(p));
    case "tags":
      return await tags(seg, p);
    case "sources":
      return json(await sources());
    case "system":
      return await system(seg);
    case "condition-types":
      return json(CONDITION_TYPES);
    default:
      return fail("not found", 404);
  }
}

/** Headline numbers for the landing page. */
async function stats() {
  const byStatus = await rows<{ status: string; n: number }>(
    `SELECT status, COUNT(*)::int AS n FROM signals GROUP BY status`,
  );

  const counts: Record<string, number> = { NEW: 0, RISING: 0, BREAKOUT: 0, FADING: 0 };
  for (const row of byStatus) counts[row.status] = row.n;

  const extra = await one(
    `SELECT
       (SELECT COUNT(DISTINCT source_id) FROM signals)::int AS sources,
       (SELECT COUNT(DISTINCT country_code) FROM signals)::int AS countries,
       (SELECT MAX(first_seen_at) FROM signals) AS last_signal_at`,
  );

  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const active = counts.NEW + counts.RISING + counts.BREAKOUT;

  return {
    total_signals: total,
    active_signals: active,
    breakout: counts.BREAKOUT,
    rising: counts.RISING,
    new: counts.NEW,
    fading: counts.FADING,
    sources: extra?.sources ?? 0,
    countries: extra?.countries ?? 0,
    last_signal_at: extra?.last_signal_at ?? null,
  };
}


/** The main feed plus per-signal routes. */
async function signals(
  url: URL,
  seg: string[],
  p: Record<string, string>,
): Promise<Response> {
  // /signals/{id}/history
  if (seg.length >= 3 && seg[2] === "history") {
    return json(await history(seg[1], p));
  }
  // /signals/{id}/related
  if (seg.length >= 3 && seg[2] === "related") {
    return await related(seg[1], intParam(p, "limit", 10));
  }
  // /signals/{id}
  if (seg.length >= 2) {
    return await signalDetail(seg[1]);
  }

  const tab = p.tab ?? "all";
  const countries = listParam(p, "country");
  const sources = listParam(p, "source");
  const tags = listParam(p, "tag");
  const keyword = p.keyword?.trim();
  const minStrength = floatParam(p, "min_strength");
  const limit = Math.min(intParam(p, "limit", 30), 100);
  const offset = intParam(p, "offset", 0);

  const where: string[] = [];
  const args: unknown[] = [];

  if (tab === "rising") where.push(`status IN ('RISING','BREAKOUT')`);
  else if (tab === "breakout") where.push(`status = 'BREAKOUT'`);
  else if (tab === "new") where.push(`status = 'NEW'`);
  else if (tab === "discover") where.push(`status IN (${ACTIVE})`);

  if (countries.length) {
    args.push(countries.map((c) => c.toUpperCase()));
    where.push(`country_code = ANY($${args.length}::varchar[])`);
  }
  if (sources.length) {
    args.push(sources);
    where.push(`source_id = ANY($${args.length}::varchar[])`);
  }
  if (tags.length) {
    args.push(tags);
    where.push(
      `EXISTS (SELECT 1 FROM json_array_elements_text(keywords) k WHERE k = ANY($${args.length}::text[]))`,
    );
  }
  if (keyword) {
    args.push(`%${keyword}%`);
    where.push(`(title ILIKE $${args.length} OR description ILIKE $${args.length})`);
  }
  if (minStrength !== null) {
    args.push(minStrength);
    where.push(`strength >= $${args.length}`);
  }

  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

  const total = await one(
    `SELECT COUNT(*)::int AS n FROM signals ${whereSql}`,
    [...args],
  );

  args.push(limit, offset);
  const limitIdx = args.length - 1;

  const items = await rows(
    `SELECT ${SIGNAL_COLUMNS} FROM signals ${whereSql}
     ORDER BY first_seen_at DESC
     LIMIT $${limitIdx} OFFSET $${limitIdx + 1}`,
    args,
  );

  return json({
    items: items.map((row) => serializeSignal(row)),
    total: total?.n ?? 0,
    limit,
    offset,
  });
}

async function signalDetail(id: string): Promise<Response> {
  const row = await one(
    `SELECT ${SIGNAL_COLUMNS} FROM signals WHERE id = $1`,
    [id],
  );
  if (!row) return fail("signal not found", 404);

  const snapshots = await rows(
    `SELECT captured_at, activity, previous_activity, growth, acceleration,
            strength, status, rank
     FROM signal_snapshots
     WHERE signal_id = $1
     ORDER BY captured_at DESC
     LIMIT 200`,
    [id],
  );

  return json({
    ...serializeSignal(row),
    snapshots: snapshots.map(serializeSnapshot),
    strength_components: null,
    source: null,
  });
}

async function history(id: string, p: Record<string, string>): Promise<Response> {
  const hours = Math.min(intParam(p, "hours", 168), 720);
  const items = await rows(
    `SELECT captured_at, activity, previous_activity, growth, acceleration,
            strength, status, rank
     FROM signal_snapshots
     WHERE signal_id = $1 AND captured_at > now() - ($2 || ' hours')::interval
     ORDER BY captured_at ASC`,
    [id, String(hours)],
  );
  return json({ items: items.map(serializeSnapshot), hours });
}


/** Signals related by shared tags, country or source. */
async function related(id: string, limit: number): Promise<Response> {
  const base = await one(
    `SELECT ${SIGNAL_COLUMNS} FROM signals WHERE id = $1`,
    [id],
  );
  if (!base) return fail("signal not found", 404);

  const baseTags = Array.isArray(base.keywords) ? (base.keywords as string[]) : [];

  const items = await rows(
    `SELECT ${SIGNAL_COLUMNS} FROM signals
     WHERE id <> $1
       AND (
         (country_code IS NOT NULL AND country_code = $2)
         OR source_id = $3
         OR EXISTS (
           SELECT 1 FROM json_array_elements_text(keywords) k
           WHERE k = ANY($4::text[])
         )
       )
     ORDER BY strength DESC
     LIMIT $5`,
    [id, base.country_code ?? null, base.source_id, baseTags, limit],
  );

  return json(items.map((row) => serializeSignal(row)));
}

/** Discovery: strongest live signals, independent of any radar. */
async function discover(p: Record<string, string>): Promise<Response> {
  const limit = Math.min(intParam(p, "limit", 40), 100);
  const where = [`status IN (${ACTIVE})`];
  const args: unknown[] = [];

  const push = (column: string, value: string | undefined) => {
    if (!value) return;
    args.push(value);
    where.push(`${column} = $${args.length}`);
  };

  push("country_code", p.country?.toUpperCase());
  push("source_id", p.source);

  if (p.tag) {
    args.push(p.tag);
    where.push(
      `EXISTS (SELECT 1 FROM json_array_elements_text(keywords) k WHERE k = $${args.length})`,
    );
  }

  args.push(limit);

  const items = await rows(
    `SELECT ${SIGNAL_COLUMNS} FROM signals
     WHERE ${where.join(" AND ")}
     ORDER BY strength DESC, growth DESC
     LIMIT $${args.length}`,
    args,
  );

  return json({
    items: items.map((row) => serializeSignal(row)),
    total: items.length,
  });
}

async function countries(p: Record<string, string>) {
  const list = p.supported_only === "true"
    ? await rows(`SELECT * FROM countries WHERE is_supported ORDER BY name`)
    : await rows(`SELECT * FROM countries ORDER BY name`);
  return list.map(serializeCountry);
}

async function tags(seg: string[], p: Record<string, string>) {
  if (seg[1] === "categories") {
    const list = await rows(
      `SELECT category, COUNT(*)::int AS count
       FROM tags GROUP BY category ORDER BY count DESC, category`,
    );
    return json(list.map((r) => ({
      category: String(r.category),
      count: Number(r.count),
    })));
  }

  const list = p.category
    ? await rows(`SELECT * FROM tags WHERE category = $1 ORDER BY name`, [p.category])
    : await rows(`SELECT * FROM tags ORDER BY name`);
  return json(list.map(serializeTag));
}

async function sources() {
  const list = await rows(`SELECT * FROM sources ORDER BY priority ASC, name ASC`);
  return json(list.map(serializeSource));
}

async function system(seg: string[]) {
  if (seg[1] !== "source-health") return fail("not found", 404);

  const items = await rows(
    `SELECT se.source_id, se.status, se.healthy_since, se.last_check_at,
            se.last_error, se.consecutive_failures, se.records_last_hour,
            se.avg_duration_ms, se.strategy, se.notes, s.name, s.type
     FROM source_health se JOIN sources s ON s.id = se.source_id
     ORDER BY s.priority ASC`,
  );

  const summary: Record<string, number> = {};
  for (const row of items) {
    const key = String(row.status);
    summary[key] = (summary[key] ?? 0) + 1;
  }
  return json({ items, summary });
}
