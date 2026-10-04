export function formatGrowth(growth: number): string {
  if (!Number.isFinite(growth)) return "0%";
  const rounded = Math.abs(growth) >= 100 ? Math.round(growth) : Math.round(growth * 10) / 10;
  return `${growth > 0 ? "+" : ""}${rounded}%`;
}

export function formatActivity(value: number, metric?: string | null): string {
  if (!Number.isFinite(value) || value <= 0) return "—";
  const short: Record<string, string> = {
    views: "views",
    approx_searches: "searches",
    posts: "posts",
    stars: "stars",
    likes: "likes",
    monthly_downloads: "dl/mo",
    reactions: "reactions",
    score_plus_comments: "score",
    query_mentions: "mentions",
    view_count: "views",
    media_count: "posts",
  };
  const suffix = metric ? (short[metric] ?? "") : "";
  return `${compact(value)}${suffix ? ` ${suffix}` : ""}`;
}

export function compact(value: number): string {
  if (!Number.isFinite(value)) return "0";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(1).replace(/\.0$/, "")}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1).replace(/\.0$/, "")}K`;
  return String(Math.round(value));
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const minutes = Math.max(0, (Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.floor(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)} h ago`;
  const days = hours / 24;
  if (days < 30) return `${Math.floor(days)} d ago`;
  return `${Math.floor(days / 30)} mo ago`;
}

export const STATUS_META: Record<
  string,
  { label: string; icon: string; tone: "new" | "rising" | "breakout" | "fading" }
> = {
  NEW: { label: "NEW", icon: "spark", tone: "new" },
  RISING: { label: "RISING", icon: "trending", tone: "rising" },
  BREAKOUT: { label: "BREAKOUT", icon: "bolt", tone: "breakout" },
  FADING: { label: "FADING", icon: "pause", tone: "fading" },
};

export const SOURCE_META: Record<string, { name: string; color: string }> = {
  tiktok: { name: "TikTok", color: "#ff2d55" },
  youtube: { name: "YouTube", color: "#ff0033" },
  instagram: { name: "Instagram", color: "#e1306c" },
  x_trends: { name: "X", color: "#8b98a8" },
  reddit: { name: "Reddit", color: "#ff4500" },
  google_trends: { name: "Google Trends", color: "#4d8dff" },
  google_news_trends: { name: "Google News", color: "#5b8cff" },
  github: { name: "GitHub", color: "#8b98a8" },
  huggingface: { name: "Hugging Face", color: "#ffcc4d" },
  producthunt: { name: "Product Hunt", color: "#da552f" },
  hackernews: { name: "Hacker News", color: "#ff6600" },
  npm: { name: "npm", color: "#cb3837" },
  devto: { name: "DEV", color: "#7ab8f5" },
  lobsters: { name: "Lobsters", color: "#e06000" },
  stackoverflow: { name: "Stack Overflow", color: "#f48024" },
};

export function sourceName(id: string): string {
  return SOURCE_META[id]?.name ?? id;
}

export function sourceColor(id: string): string {
  return SOURCE_META[id]?.color ?? "var(--text-3)";
}

export function strengthTone(strength: number): "low" | "mid" | "high" {
  if (strength >= 70) return "high";
  if (strength >= 45) return "mid";
  return "low";
}

/** "South Korea" from "KR" so the card reads like the spec example. */
const COUNTRY_NAMES: Record<string, string> = {
  KR: "South Korea", JP: "Japan", US: "United States", GB: "United Kingdom",
  CN: "China", TW: "Taiwan", HK: "Hong Kong", TR: "Turkey", AE: "UAE",
  AZ: "Azerbaijan", BR: "Brazil", IN: "India", DE: "Germany", FR: "France",
  ES: "Spain", IT: "Italy", MX: "Mexico", CA: "Canada", AU: "Australia",
  RU: "Russia", SG: "Singapore", ID: "Indonesia", PH: "Philippines",
  TH: "Thailand", VN: "Vietnam", MY: "Malaysia", PL: "Poland", NL: "Netherlands",
  SE: "Sweden", PT: "Portugal", UA: "Ukraine", SA: "Saudi Arabia",
  IL: "Israel", ZA: "South Africa", NG: "Nigeria", EG: "Egypt",
  KZ: "Kazakhstan", AR: "Argentina", CL: "Chile", CO: "Colombia",
  PE: "Peru", NZ: "New Zealand", IE: "Ireland", RO: "Romania",
  GR: "Greece", PK: "Pakistan", BD: "Bangladesh", IR: "Iran", QA: "Qatar",
};

export function countryName(code: string | null | undefined): string {
  if (!code) return "Global";
  return COUNTRY_NAMES[code] ?? code;
}

/** "18 min ago" for the "First detected" line. */
export function firstDetected(iso: string | null | undefined): string {
  return timeAgo(iso);
}