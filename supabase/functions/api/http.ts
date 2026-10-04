/** Shared HTTP helpers: CORS, JSON responses, route parsing. */

export const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, PUT, OPTIONS",
  "Access-Control-Allow-Headers":
    "Authorization, Content-Type, apikey, x-client-info",
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

export function fail(detail: string, status = 400): Response {
  return json({ detail }, status);
}

export function preflight(): Response {
  return new Response("ok", { headers: CORS_HEADERS });
}

/** Turn a URL path into segments, dropping empty ones. */
export function segments(url: URL): string[] {
  return url.pathname.split("/").filter(Boolean);
}

/** Query params as a plain object of strings. */
export function params(url: URL): Record<string, string> {
  const out: Record<string, string> = {};
  url.searchParams.forEach((value, key) => {
    out[key] = value;
  });
  return out;
}

export function listParam(p: Record<string, string>, key: string): string[] {
  const value = p[key];
  if (!value) return [];
  return value.split(",").map((s) => s.trim()).filter(Boolean);
}

export function intParam(
  p: Record<string, string>,
  key: string,
  fallback: number,
): number {
  const raw = p[key];
  if (raw === undefined) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function floatParam(
  p: Record<string, string>,
  key: string,
): number | null {
  const raw = p[key];
  if (raw === undefined || raw === "") return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function body(request: Request): Promise<Record<string, unknown>> {
  try {
    const parsed = await request.json();
    return (parsed ?? {}) as Record<string, unknown>;
  } catch {
    return {};
  }
}