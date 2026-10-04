/**
 * Postgres access for the edge function.
 *
 * Uses the Supabase pooler in transaction mode (port 6543). A direct
 * connection would open a new TCP connection per cold start and exhaust the
 * project connection limit (60 on the free plan).
 */

import postgres from "npm:postgres@3.4.5";

const projectRef = Deno.env.get("SUPABASE_PROJECT_REF") ?? "qtozkhuqaqnglztaalkx";
const region = Deno.env.get("SUPABASE_REGION") ?? "eu-central-1";
const password = Deno.env.get("DB_PASSWORD") ?? "";

let client: ReturnType<typeof postgres> | null = null;

function connectionString(): string {
  if (password) {
    return `postgres://postgres.${projectRef}:${encodeURIComponent(
      password,
    )}@aws-0-${region}.pooler.supabase.com:6543/postgres?pgbouncer=true&connect_timeout=10`;
  }
  throw new Error("DB_PASSWORD is not set on the edge function");
}

/** Lazily create the shared client; Deno reuses it across warm invocations. */
export function db() {
  if (!client) {
    client = postgres(connectionString(), {
      max: 1,
      idle_timeout: 20,
      connect_timeout: 10,
      prepare: false, // required by pgbouncer transaction mode
      onnotice: () => {},
    });
  }
  return client;
}

/** Run rows as plain objects rather than postgres.js tuples. */
export async function rows<T = Record<string, unknown>>(
  sql: TemplateStringsArray | string,
  params: unknown[] = [],
): Promise<T[]> {
  const client = db();
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
  const client = db();
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