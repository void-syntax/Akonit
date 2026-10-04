export type SignalStatus = "NEW" | "RISING" | "BREAKOUT" | "FADING";

export type SourceStatus =
  | "ACTIVE"
  | "DEGRADED"
  | "OFFLINE"
  | "OPTIONAL_CREDENTIALS";

export type NotificationFrequency =
  | "OFF"
  | "INSTANT"
  | "EVERY_15_MIN"
  | "HOURLY"
  | "DAILY_DIGEST";

export interface Signal {
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
  status: SignalStatus;
  strength: number;
  age_minutes: number;
  activity_metric: string | null;
  keywords: string[];
  is_saved: boolean;
  is_ignored: boolean;
}

export interface Snapshot {
  captured_at: string;
  activity: number;
  previous_activity: number;
  growth: number;
  acceleration: number;
  strength: number;
  status: SignalStatus;
  rank: number | null;
}

export interface SignalDetail extends Signal {
  source_metadata: Record<string, unknown>;
  snapshots: Snapshot[];
}

export interface SignalPage {
  items: Signal[];
  total: number;
  limit: number;
  offset: number;
}

export interface Country {
  code: string;
  alpha3: string;
  name: string;
  slug: string;
  flag: string;
  region: string | null;
  is_supported: boolean;
}

export interface SourceInfo {
  id: string;
  name: string;
  type: string;
  description: string | null;
  enabled: boolean;
  status: SourceStatus;
  status_reason: string | null;
  cost: string;
  credentials_required: boolean;
  capabilities: string[];
  priority: number;
  strategy: string | null;
  last_fetch: string | null;
  last_success: string | null;
  records_fetched: number;
  total_records: number;
  error_count: number;
  last_error: string | null;
}

export interface Tag {
  slug: string;
  name: string;
  category: string;
  emoji: string | null;
  description: string | null;
}

export interface Radar {
  id: string;
  name: string;
  emoji: string | null;
  description: string | null;
  countries: string[];
  source_ids: string[];
  tag_slugs: string[];
  signal_threshold: number;
  notification_frequency: NotificationFrequency;
  notification_channels: string[];
  is_active: boolean;
  match_count: number;
  active_signal_count: number;
  last_matched_at: string | null;
  created_at: string;
}

export interface CustomTag {
  id: string;
  name: string;
  slug: string;
  keywords: string[];
  aliases: string[];
  hashtags: string[];
  country_codes: string[];
  source_ids: string[];
  excludes: string[];
  exclude_hashtags: string[];
  exclude_countries: string[];
  emoji: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CustomTagDraft {
  name: string;
  keywords: string[];
  aliases: string[];
  hashtags: string[];
  country_codes: string[];
  source_ids: string[];
  excludes: string[];
  exclude_hashtags: string[];
  exclude_countries: string[];
  emoji?: string | null;
}

export interface Profile {
  display_name: string | null;
  timezone: string;
  language: string;
  telegram_chat_id: string | null;
  default_frequency: NotificationFrequency;
  onboarded: boolean;
  signal_threshold: number;
  default_countries: string[];
  default_sources: string[];
  default_tags: string[];
  quiet_hours: { start: string; end: string; enabled: boolean } | null;
  theme: string;
}

export interface PublicStats {
  total_signals: number;
  active_signals: number;
  breakout: number;
  rising: number;
  new: number;
  fading: number;
  sources: number;
  countries: number;
  last_signal_at: string | null;
}

export interface RadarSummary {
  radar_id: string;
  parts: string[];
  threshold: number;
  frequency: NotificationFrequency;
}

export interface NotificationStatus {
  linked: boolean;
  chat_id: string | null;
  bot_configured: boolean;
  push_configured: boolean;
}

/* --- condition AST --- */
export type ConditionType =
  | "COUNTRY"
  | "SOURCE"
  | "TAG"
  | "KEYWORD"
  | "GROWTH"
  | "ACTIVITY"
  | "AGE"
  | "STATUS"
  | "STRENGTH";

export type ConditionOperator =
  | "IN"
  | "NOT_IN"
  | "GT"
  | "GTE"
  | "LT"
  | "LTE"
  | "EQ"
  | "CONTAINS";

export interface Condition {
  type: ConditionType;
  operator: ConditionOperator;
  value?: unknown;
  unit?: string | null;
}

export interface ConditionGroup {
  op: "AND" | "OR" | "NOT";
  children: (ConditionGroup | Condition)[];
  is_exclude?: boolean;
}

export interface ConditionOption {
  type: ConditionType;
  operators: string[];
  unit_options?: string[] | null;
  description: string;
}

export interface SourceHealthReport {
  summary: Record<SourceStatus, number>;
  sources: (SourceInfo & {
    consecutive_failures: number;
    notes: string | null;
  })[];
}