export type SignalStatus = "NEW" | "RISING" | "BREAKOUT" | "UNICORN_SIGNAL" | "FADING";

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
  cross_source_urls: string[];
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
  velocity: number;
  density_count: number;

  // AI classification (Laya)
  ai_priority?: 'critical' | 'watch' | 'noise' | null;
  ai_priority_score?: number;
  ai_category?: string | null;
  ai_should_notify?: number;
  ai_noise_probability?: number;
  ai_trending_score?: number;
}

export interface IntelligenceBriefing {
  id: string;
  signal_id: string;
  core_thesis: string;
  alpha_potential: string;
  monetization_strategy: string;
  risk_analysis: string;
  sources_synthesized: string[];
  confidence_score: number;
  model_used: string;
  created_at: string;
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

export interface RadarCondition {
  id?: string;
  type: string;
  operator: string;
  value: any;
  unit?: string | null;
}

export interface ConditionGroup {
  id?: string;
  op?: string;
  join?: "AND" | "OR";
  is_exclude?: boolean;
  conditions?: RadarCondition[];
  children?: (RadarCondition | ConditionGroup)[];
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

export interface RadarSummary extends Radar {
  matches?: Signal[];
  parts?: string[];
}

export interface ConditionOption {
  type: string;
  operators: string[];
  unit_options: string[] | null;
  description: string;
}

export interface Profile {
  display_name: string | null;
  timezone: string;
  language: string;
  telegram_chat_id: string | null;
  telegram_alerts_enabled: boolean;
  default_frequency: NotificationFrequency;
  onboarded: boolean;
  signal_threshold: number;
  default_countries: string[];
  default_sources: string[];
  default_tags: string[];
  collector_source_weights: Record<string, number>;
  collector_keywords: string[];
  quiet_hours: Record<string, unknown> | null;
  theme: string;
}

export interface PublicStats {
  active_radars: number;
  signals_monitored: number;
  total_signals?: number;
  notifications_sent: number;
  active_sources: number;
  sources?: number;
  countries?: number;
  breakout?: number;
}

export type ConditionType =
  | "COUNTRY"
  | "SOURCE"
  | "TAG"
  | "KEYWORD"
  | "GROWTH"
  | "ACTIVITY"
  | "AGE"
  | "STATUS"
  | "STRENGTH"
  | "VELOCITY"
  | "DENSITY";

export interface SourceHealthReport {
  sources: SourceInfo[];
  ok_count: number;
  failed_count: number;
}

export interface NotificationStatus {
  enabled: boolean;
  supported: boolean;
  push_configured?: boolean;
  bot_configured?: boolean;
  linked?: boolean;
  chat_id?: string | null;
  alerts_enabled?: boolean;
}
