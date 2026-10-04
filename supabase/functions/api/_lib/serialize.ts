/**
 * Row -> API shape.
 *
 * Field names and types must match the Python schemas exactly, because the
 * frontend consumes both without knowing which backend answered.
 */

export type Row = Record<string, unknown>;

function asArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((v) => String(v));
  // Postgres JSON columns arrive as a string when read as text.
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.map((v) => String(v)) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function num(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function str(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

export interface SignalOut {
  id: string;
  title: string;
  description: string;
  category: string | null;
  hashtags: string[];
  country_code: string | null;
  country_name: string | null;
  flag: string | null;
  source_id: string;
  source_url: string;
  thumbnail: string | null;
  cross_source_count: number;
  first_seen_at: string;
  last_seen_at: string;
  current_activity: number;
  previous_activity: number;
  growth: number;
  acceleration: number;
  status: string;
  strength: number;
  age_minutes: number;
  activity_metric: string | null;
  keywords: string[];
  is_saved: boolean;
  is_ignored: boolean;
  velocity: number;
  density_count: number;
}

export function serializeSignal(
  row: Row,
  saved: Set<string> = new Set(),
  ignored: Set<string> = new Set(),
): SignalOut {
  const id = String(row.id);
  return {
    id,
    title: String(row.title ?? ""),
    description: String(row.description ?? ""),
    category: str(row.category),
    hashtags: asArray(row.hashtags),
    country_code: str(row.country_code),
    country_name: str(row.country_name),
    flag: str(row.flag),
    source_id: String(row.source_id ?? ""),
    source_url: String(row.source_url ?? ""),
    thumbnail: str(row.thumbnail),
    cross_source_count: num(row.cross_source_count, 1),
    first_seen_at: String(row.first_seen_at),
    last_seen_at: String(row.last_seen_at),
    current_activity: num(row.current_activity),
    previous_activity: num(row.previous_activity),
    growth: num(row.growth),
    acceleration: num(row.acceleration),
    status: String(row.status ?? "NEW"),
    strength: num(row.strength),
    age_minutes: num(row.age_minutes),
    activity_metric: str(row.activity_metric),
    keywords: asArray(row.keywords),
    is_saved: saved.has(id),
    is_ignored: ignored.has(id),
    velocity: num(row.velocity),
    density_count: num(row.density_count, 1),
  };
}

export function serializeCountry(row: Row) {
  return {
    code: String(row.code),
    alpha3: String(row.alpha3 ?? ""),
    name: String(row.name),
    slug: String(row.slug ?? ""),
    flag: String(row.flag ?? ""),
    region: str(row.region),
    is_supported: Boolean(row.is_supported),
  };
}

export function serializeTag(row: Row) {
  return {
    id: String(row.id),
    slug: String(row.slug),
    name: String(row.name),
    category: String(row.category ?? ""),
    emoji: str(row.emoji),
    description: str(row.description),
    is_system: Boolean(row.is_system),
  };
}

export function serializeSource(row: Row) {
  return {
    id: String(row.id),
    name: String(row.name),
    type: String(row.type),
    adapter: String(row.adapter ?? ""),
    description: str(row.description),
    enabled: Boolean(row.enabled),
    status: String(row.status),
    status_reason: str(row.status_reason),
    cost: String(row.cost ?? "FREE"),
    credentials_required: Boolean(row.credentials_required),
    capabilities: asArray(row.capabilities),
    priority: num(row.priority),
    collect_interval_seconds: num(row.collect_interval_seconds),
    records_fetched: num(row.records_fetched),
    total_records: num(row.total_records),
    last_fetch: str(row.last_fetch),
    last_success: str(row.last_success),
    last_error: str(row.last_error),
    error_count: num(row.error_count),
    strategy: str(row.strategy),
  };
}

export function serializeProfile(row: Row) {
  return {
    display_name: str(row.display_name),
    timezone: String(row.timezone ?? "UTC"),
    language: String(row.language ?? "en"),
    telegram_chat_id: str(row.telegram_chat_id),
    default_frequency: String(row.default_frequency ?? "INSTANT"),
    onboarded: Boolean(row.onboarded),
    signal_threshold: num(row.signal_threshold),
    default_countries: asArray(row.default_countries),
    default_sources: asArray(row.default_sources),
    default_tags: asArray(row.default_tags),
    quiet_hours: row.quiet_hours ?? null,
    theme: String(row.theme ?? "dark"),
  };
}

export function serializeSnapshot(row: Row) {
  return {
    captured_at: String(row.captured_at),
    activity: num(row.activity),
    previous_activity: num(row.previous_activity),
    growth: num(row.growth),
    acceleration: num(row.acceleration),
    strength: num(row.strength),
    status: String(row.status),
    rank: row.rank === null || row.rank === undefined ? null : num(row.rank),
  };
}