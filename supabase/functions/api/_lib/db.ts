/**
 * Postgres access for the edge function.
 *
 * Connection string resolution, in order:
 *   1. SUPABASE_DB_URL - injected automatically into every hosted edge function.
 *      Preferred: the platform keeps it correct even when the pooler host, the
 *      username format or the region changes.
 *   2. A pooler URL built from DB_PASSWORD. Needed only for `supabase functions
 *      serve` locally, where the automatic variable is absent.
 *
 * The pooler runs in transaction mode (port 6543) because the free plan allows
 * only 60 Postgres connections. A direct connection would open a new TCP
 * connection per cold start and exhaust that limit.
 */

import postgres from "npm:postgres@3.4.5";

const projectRef = Deno.env.get("SUPABASE_PROJECT_REF") ?? "qtozkhuqaqnglztaalkx";
const region = Deno.env.get("SUPABASE_REGION") ?? "eu-central-1";
const password = Deno.env.get("DB_PASSWORD") ?? "";

let client: ReturnType<typeof postgres> | null = null;

/**
 * Candidate connection strings, best first.
 *
 * The direct endpoint (SUPABASE_DB_URL) is IPv6-only, which not every runtime
 * can reach, so the pooler stays a working fallback rather than a comment.
 */
function candidates(): string[] {
  const list: string[] = [];
  const direct = Deno.env.get("SUPABASE_DB_URL");
  if (direct) list.push(direct);
  if (password) {
    list.push(
      `postgres://postgres.${projectRef}:${encodeURIComponent(
        password,
      )}@aws-0-${region}.pooler.supabase.com:6543/postgres?pgbouncer=true&connect_timeout=10`,
    );
  }
  if (list.length === 0) {
    throw new Error(
      "No database URL: set SUPABASE_DB_URL (automatic when hosted) or DB_PASSWORD",
    );
  }
  return list;
}

function options() {
  return {
    max: 1,
    idle_timeout: 20,
    connect_timeout: 10,
    prepare: false, // required by pgbouncer transaction mode
    onnotice: () => {},
  };
}

let connecting: Promise<ReturnType<typeof postgres>> | null = null;

/**
 * Lazily create the shared client, trying each candidate once.
 *
 * The result is memoised so a warm isolate reuses one connection instead of
 * reconnecting on every request.
 */
export function db() {
  if (client) return client;
  if (connecting) return connecting;

  connecting = (async () => {
    const urls = candidates();
    let lastError: unknown;

    for (const url of urls) {
      const attempt = postgres(url, options());
      try {
        await attempt`SELECT 1`;
        client = attempt;
        connecting = null;
        return attempt;
      } catch (error) {
        lastError = error;
        await attempt.end({ timeout: 1 }).catch(() => {});
        console.error(
          "db connection failed, trying next candidate",
          url.split("@")[1] ?? url,
          error instanceof Error ? error.message : error,
        );
      }
    }

    connecting = null;
    throw lastError instanceof Error
      ? lastError
      : new Error("no database connection could be established");
  })();

  return connecting;
}

/** Run rows as plain objects rather than postgres.js tuples. */
export async function rows<T = Record<string, unknown>>(
  sql: TemplateStringsArray | string,
  params: unknown[] = [],
): Promise<T[]> {
  const client = await db();
  const query =
    typeof sql === "string" ? client.unsafe(sql, params as never[]) : client(sql, params as never[]);
  return (await query) as T[];
}

/** Run a statement and return the first row, or null. */
export async function one<T = Record<string, unknown>>(
  sql: TemplateStringsArray | string,
  params: unknown[] = [],
): Promise<T | null> {
  const result = await rows<T>(sql, params);
  return result.length > 0 ? result[0] : null;
}

/** Convenience for statements that return nothing useful. */
export async function exec(
  sql: TemplateStringsArray | string,
  params: unknown[] = [],
): Promise<void> {
  const client = await db();
  if (typeof sql === "string") {
    await client.unsafe(sql, params as never[]);
  } else {
    await client(sql, params as never[]);
  }
}

export function newId(): string {
  return crypto.randomUUID();
}

export function nowIso(): string {
  return new Date().toISOString();
}