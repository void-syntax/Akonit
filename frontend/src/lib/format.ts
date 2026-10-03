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
  { label: string; emoji: string; className: string }
> = {
  NEW: { label: "NEW", emoji: "🆕", className: "status-new" },
  RISING: { label: "RISING", emoji: "📈", className: "status-rising" },
  BREAKOUT: { label: "BREAKOUT", emoji: "🚨", className: "status-breakout" },
  FADING: { label: "FADING", emoji: "💤", className: "status-fading" },
};

export const SOURCE_META: Record<string, { name: string; emoji: string }> = {
  tiktok: { name: "TikTok", emoji: "🎵" },
  youtube: { name: "YouTube", emoji: "▶️" },
  instagram: { name: "Instagram", emoji: "📸" },
  x_trends: { name: "X", emoji: "𝕏" },
  reddit: { name: "Reddit", emoji: "👽" },
  google_trends: { name: "Google Trends", emoji: "🔍" },
  google_news_trends: { name: "Google News", emoji: "📰" },
  github: { name: "GitHub", emoji: "🐙" },
  huggingface: { name: "Hugging Face", emoji: "🤗" },
  producthunt: { name: "Product Hunt", emoji: "🚀" },
  hackernews: { name: "Hacker News", emoji: "🟧" },
  npm: { name: "npm", emoji: "📦" },
  devto: { name: "DEV", emoji: "✍️" },
  lobsters: { name: "Lobsters", emoji: "🦞" },
  stackoverflow: { name: "Stack Overflow", emoji: "📚" },
};

export function sourceName(id: string): string {
  return SOURCE_META[id]?.name ?? id;
}

export function strengthTone(strength: number): "low" | "mid" | "high" {
  if (strength >= 70) return "high";
  if (strength >= 45) return "mid";
  return "low";
}