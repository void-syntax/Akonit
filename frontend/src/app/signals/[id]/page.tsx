"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ActivityChart } from "@/components/ActivityChart";
import { SignalCard } from "@/components/SignalCard";
import {
  BookmarkIcon,
  BoltIcon,
  ExternalIcon,
  LayersIcon,
  PauseIcon,
  SparkIcon,
  TrendingUpIcon,
} from "@/components/icons";
import { api } from "@/lib/api";
import {
  STATUS_META,
  countryName,
  formatActivity,
  formatGrowth,
  sourceColor,
  sourceName,
  strengthTone,
  timeAgo,
} from "@/lib/format";
import type { Signal, SignalDetail } from "@/lib/types";

const STATUS_ICON = {
  spark: SparkIcon,
  trending: TrendingUpIcon,
  bolt: BoltIcon,
  pause: PauseIcon,
} as const;

export default function SignalPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [signal, setSignal] = useState<SignalDetail | null>(null);
  const [related, setRelated] = useState<Signal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [muted, setMuted] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const detail = await api.signal(params.id);
        setSignal(detail);
        setSaved(detail.is_saved);
        setMuted(detail.is_ignored);
        try {
          setRelated(await api.related(params.id, 4));
        } catch {
          setRelated([]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Signal not found");
      }
    })();
  }, [params.id]);

  async function toggleSave() {
    if (!signal) return;
    setBusy(true);
    try {
      if (saved) {
        await api.unsave(signal.id);
        setSaved(false);
      } else {
        await api.save(signal.id);
        setSaved(true);
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggleMute() {
    if (!signal) return;
    setBusy(true);
    try {
      if (muted) {
        await api.unmute(signal.id);
        setMuted(false);
      } else {
        await api.mute(signal.id);
        setMuted(true);
      }
    } finally {
      setBusy(false);
    }
  }

  if (error && !signal) {
    return (
      <div className="empty">
        <div className="empty-title">Signal unavailable</div>
        <p className="empty-text">{error}</p>
        <Link className="btn" href="/">
          Back to feed
        </Link>
      </div>
    );
  }

  if (!signal) return <p className="muted">Loading signal…</p>;

  const meta = STATUS_META[signal.status] ?? STATUS_META.NEW;
  const StatusIcon = STATUS_ICON[meta.icon as keyof typeof STATUS_ICON];
  const tone = strengthTone(signal.strength);

  const metrics: [string, string][] = [
    ["Category", signal.category ?? "—"],
    ["Country", `${signal.flag ?? "🌐"} ${countryName(signal.country_code)}`],
    ["Source", sourceName(signal.source_id)],
    ["First detected", timeAgo(signal.first_seen_at)],
    ["Signal age", timeAgo(signal.first_seen_at)],
    ["Last seen", timeAgo(signal.last_seen_at)],
    [
      "Current activity",
      formatActivity(signal.current_activity, signal.activity_metric),
    ],
    [
      "Previous activity",
      formatActivity(signal.previous_activity, signal.activity_metric),
    ],
    ["Growth", formatGrowth(signal.growth)],
    ["Acceleration", formatGrowth(signal.acceleration)],
    ["Strength", `${Math.round(signal.strength)}/100`],
    ["Cross-source", String(signal.cross_source_count)],
  ];

  return (
    <>
      <div className="row" style={{ marginBottom: "var(--s3)" }}>
        <button className="btn btn-sm btn-ghost" onClick={() => router.back()}>
          ← Back
        </button>
      </div>

      <div className="panel">
        <div className="card-top">
          <span className={`badge badge-${meta.tone}`}>
            <StatusIcon size={13} />
            {meta.label}
          </span>
          <span className="badge badge-neutral">
            {signal.flag ?? "🌐"} {countryName(signal.country_code)}
          </span>
          <span
            className="badge badge-neutral"
            style={{ color: sourceColor(signal.source_id) }}
          >
            {sourceName(signal.source_id)}
          </span>
          <span
            className="badge badge-growth"
            data-tone={signal.growth > 0 ? "up" : "down"}
          >
            {formatGrowth(signal.growth)}
          </span>
        </div>

        <h1
          style={{
            fontSize: "var(--t-21)",
            lineHeight: 1.32,
            margin: "0 0 var(--s2)",
            letterSpacing: "-0.02em",
          }}
        >
          {signal.title}
        </h1>

        {signal.description && (
          <p className="muted text-sm" style={{ margin: "0 0 var(--s3)" }}>
            {signal.description}
          </p>
        )}

        {signal.keywords.length > 0 && (
          <div className="card-tags">
            {signal.keywords.map((tag) => (
              <span key={tag} className="tag-chip">
                {tag.replace(/-/g, " ")}
              </span>
            ))}
          </div>
        )}

        <div className="row" style={{ marginTop: "var(--s3)" }}>
          <span className="strength">
            <span className="strength-bar">
              <span
                className="strength-fill"
                data-tone={tone}
                style={{ width: `${Math.min(signal.strength, 100)}%` }}
              />
            </span>
            {Math.round(signal.strength)}
          </span>
          <div className="spacer" />
          <a
            className="btn btn-primary"
            href={signal.source_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open original source <ExternalIcon size={14} />
          </a>
          <button
            className="btn"
            data-active={saved}
            onClick={toggleSave}
            disabled={busy}
          >
            <BookmarkIcon size={14} filled={saved} /> {saved ? "Saved" : "Save"}
          </button>
          <button
            className="btn"
            data-active={muted}
            onClick={toggleMute}
            disabled={busy}
          >
            <PauseIcon size={14} /> {muted ? "Hidden" : "Mute"}
          </button>
        </div>
      </div>

      <div className="section-title">Activity history</div>
      <div className="panel">
        <ActivityChart
          points={signal.snapshots.map((s) => ({
            t: s.captured_at,
            activity: s.activity,
          }))}
        />

        {signal.snapshots.length > 0 && (
          <div className="metric-grid" style={{ marginTop: "var(--s4)" }}>
            {signal.snapshots.slice(-4).reverse().map((s) => (
              <div className="metric" key={s.captured_at}>
                <div className="metric-label">{timeAgo(s.captured_at)}</div>
                <div className="metric-value mono">
                  {formatActivity(s.activity, signal.activity_metric)}
                </div>
                <div
                  className="text-xs mono"
                  style={{
                    color: s.growth > 0 ? "var(--ok)" : "var(--text-3)",
                  }}
                >
                  {formatGrowth(s.growth)} · str {Math.round(s.strength)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="section-title">Details</div>
      <div className="panel">
        <div className="metric-grid">
          {metrics.map(([label, value]) => (
            <div className="metric" key={label}>
              <div className="metric-label">{label}</div>
              <div
                className="metric-value mono"
                style={{ fontSize: "var(--t-15)" }}
              >
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>

      {related.length > 0 && (
        <>
          <div className="section-title">
            <LayersIcon size={13} /> Related signals
          </div>
          {related.map((item) => (
            <SignalCard key={item.id} signal={item} />
          ))}
        </>
      )}
    </>
  );
}