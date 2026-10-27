import type {
  ConditionGroup,
  ConditionOption,
  Country,
  CustomTag,
  CustomTagDraft,
  NotificationFrequency,
  NotificationStatus,
  Profile,
  PublicStats,
  Radar,
  RadarSummary,
  Signal,
  SignalDetail,
  SignalPage,
  SourceHealthReport,
  SourceInfo,
  Tag,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BASE = `${API_URL}/api/v1`;

let accessToken: string | null = null;

export function setToken(token: string | null) {
  accessToken = token;
  if (typeof window !== "undefined") {
    if (token) window.localStorage.setItem("sr_token", token);
    else window.localStorage.removeItem("sr_token");
  }
}

export function getToken(): string | null {
  if (accessToken) return accessToken;
  if (typeof window !== "undefined") {
    accessToken = window.localStorage.getItem("sr_token");
  }
  return accessToken;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  // No `credentials: "include"`. The API is cross-origin in production
  // (vercel.app -> supabase.co) and answers with `Access-Control-Allow-Origin: *`;
  // the browser rejects a credentialed response to a wildcard origin, so every
  // request would fail CORS. Auth is a bearer token from localStorage, so no
  // cookie is ever needed.
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      headers,
      cache: "no-store",
    });
  } catch (err) {
    // Preserve fetch cancellation: callers use AbortController when filters
    // change or a page unmounts, and should not surface that as an API outage.
    if (
      options.signal?.aborted ||
      (err instanceof Error && err.name === "AbortError")
    ) {
      throw err;
    }
    throw new ApiError(0, err instanceof Error ? err.message : "Network request failed");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let data: any = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError(response.status, "Invalid JSON response");
    }
  }

  if (!response.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join("; ")
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

function qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(","));
    } else {
      search.set(key, String(value));
    }
  }
  const str = search.toString();
  return str ? `?${str}` : "";
}

export interface FeedQuery {
  tab?: "all" | "new" | "rising" | "breakout" | "discover" | "saved";
  country?: string[];
  source?: string[];
  /** Tag slugs; the feed only returns signals carrying them. */
  tag?: string[];
  keyword?: string;
  min_strength?: number;
  max_age_minutes?: number;
  radar_id?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  /** Exposed so Settings can show which API the app is talking to. */
  baseUrl: () => BASE,

  me: () => request<{ id: string; email: string }>("/auth/me"),

  countries: (q?: string, supportedOnly = false) =>
    request<Country[]>(
      `/countries${qs({ q, supported_only: supportedOnly || undefined })}`,
    ),

  sources: () => request<SourceInfo[]>("/sources"),

  sourceHealth: () => request<SourceHealthReport>("/system/source-health"),

  tags: (category?: string) => request<Tag[]>(`/tags${qs({ category })}`),

  tagCategories: () =>
    request<{ category: string; count: number }[]>("/tags/categories"),

  conditionTypes: () => request<ConditionOption[]>("/condition-types"),

  signals: (query: FeedQuery = {}, init?: RequestInit) =>
    request<SignalPage>(`/signals${qs(query as Record<string, unknown>)}`, init),

  signal: (id: string) => request<SignalDetail>(`/signals/${id}`),

  related: (id: string, limit = 6) =>
    request<Signal[]>(`/signals/${id}/related${qs({ limit })}`),

  discover: (
    query: {
      limit?: number;
      country?: string[];
      source?: string[];
      tag?: string[];
      min_strength?: number;
    } = {},
    init?: RequestInit,
  ) =>
    request<{ items: Signal[]; total: number }>(
      `/discover${qs(query as Record<string, unknown>)}`,
      init,
    ),

  stats: () => request<PublicStats>("/stats"),

  profile: () => request<Profile>("/auth/profile"),

  updateProfile: (payload: Record<string, unknown>) =>
    request<Profile>("/auth/profile", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  notificationStatus: () => request<NotificationStatus>("/notifications/telegram/status"),

  configureTelegramBot: (token: string) =>
    request<{ ok: boolean; bot_username?: string }>("/notifications/telegram/bot", {
      method: "PUT",
      body: JSON.stringify({ token }),
    }),

  removeTelegramBot: () =>
    request<{ ok: boolean }>("/notifications/telegram/bot", { method: "DELETE" }),

  testTelegram: () =>
    request<{ ok: boolean }>("/notifications/telegram/test", { method: "POST" }),

  findTelegramChat: () =>
    request<{ chat_id: string; name?: string | null }>("/notifications/telegram/find-chat", {
      method: "POST",
    }),

  toggleTelegram: (enabled: boolean) =>
    request<{ ok: boolean; telegram_alerts_enabled: boolean }>(
      `/notifications/telegram/toggle?enabled=${enabled}`, { method: "POST" },
    ),

  linkTelegram: (chatId: string) =>
    request<{ ok: boolean }>(`/notifications/telegram/link${qs({ chat_id: chatId })}`, {
      method: "POST",
    }),

  pushPublicKey: () =>
    request<{ public_key: string }>("/notifications/push/public-key"),

  subscribePush: (payload: {
    endpoint: string;
    keys: Record<string, string>;
  }) =>
    request<{ ok: boolean }>("/notifications/push/subscribe", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  unsubscribePush: (endpoint: string) =>
    request<{ ok: boolean }>("/notifications/push/subscribe", {
      method: "DELETE",
      body: JSON.stringify({ endpoint }),
    }),

  history: (id: string) =>
    request<{ signal_id: string; points: Record<string, unknown>[] }>(
      `/signals/${id}/history`,
    ),

  save: (id: string) => request<Signal>(`/signals/${id}/save`, { method: "POST" }),

  unsave: (id: string) => request<void>(`/signals/${id}/save`, { method: "DELETE" }),

  mute: (id: string) => request<Signal>(`/signals/${id}/mute`, { method: "POST" }),

  unmute: (id: string) =>
    request<void>(`/signals/${id}/mute`, { method: "DELETE" }),

  deleteSignal: (id: string) =>
    request<void>(`/signals/${id}`, { method: "DELETE" }),

  saved: () => request<Signal[]>("/saved"),

  radars: () => request<Radar[]>("/radars"),

  createRadar: (payload: Record<string, unknown>) =>
    request<Radar>("/radars", { method: "POST", body: JSON.stringify(payload) }),

  updateRadar: (id: string, payload: Record<string, unknown>) =>
    request<Radar>(`/radars/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteRadar: (id: string) =>
    request<void>(`/radars/${id}`, { method: "DELETE" }),

  radarConditions: (id: string) =>
    request<{ radar_id: string; ast: ConditionGroup; threshold: number }>(
      `/radars/${id}/conditions`,
    ),

  previewConditions: (conditions: ConditionGroup) =>
    request<{ matched: number; items: Signal[] }>("/radars/preview", {
      method: "POST",
      body: JSON.stringify({ conditions }),
    }),

  runRadar: (id: string) =>
    request<{ evaluated: number; matched: number }>(`/radars/${id}/run`, {
      method: "POST",
    }),

  radarSummary: (id: string) =>
    request<RadarSummary>(`/radars/${id}/summary`),

  customTags: () => request<CustomTag[]>("/custom-tags"),

  customTagPreview: (draft: CustomTagDraft) =>
    request<{ matched: number }>("/custom-tags/preview", {
      method: "POST",
      body: JSON.stringify(draft),
    }),

  createCustomTag: (payload: CustomTagDraft) =>
    request<CustomTag>("/custom-tags", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateCustomTag: (id: string, payload: CustomTagDraft) =>
    request<CustomTag>(`/custom-tags/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteCustomTag: (id: string) =>
    request<void>(`/custom-tags/${id}`, { method: "DELETE" }),

  collectNow: (countries?: string) =>
    request<Record<string, unknown>>(`/system/collect${qs({ countries })}`, {
      method: "POST",
    }),

  pauseWorker: () =>
    request<{ status: string }>("/system/pause", {
      method: "POST",
    }),

  resumeWorker: () =>
    request<{ status: string }>("/system/resume", {
      method: "POST",
    }),

  workerStatus: () =>
    request<{ running: boolean; paused: boolean }>("/system/worker-status"),

  adminStats: () =>
    request<{
      total_signals: number;
      active_websocket_connections: number;
      dlq_size: number;
      cache_hits: number;
      cache_misses: number;
      service: string;
      status: string;
    }>("/admin/stats"),

  telemetryMetrics: () =>
    request<{
      signals?: { total?: number };
      sources?: { active_24h?: number };
      database?: { status?: string; page_count?: number; freelist_count?: number };
    }>("/telemetry/metrics"),
};
