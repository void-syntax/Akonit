"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import {
  STATUS_META,
  compact,
  formatActivity,
  formatGrowth,
  sourceName,
  strengthTone,
  timeAgo,
} from "@/lib/format";
import type { SignalDetail } from "@/lib/types";

function Sparkline({ points }: { points: { t: string; activity: number }[] }) {
  if (points.length < 2) {
    return (
      <p className="dim" style={{ fontSize: "0.8rem" }}>
        Collecting history — the chart appears after the second snapshot.
      </p>
    );
  }

  const values = points.map((p) => p.activity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 600;
  const height = 120;

  const coords = values.map((value, index) => ({
    x: (index / (values.length - 1)) * width,
    y: height - ((value - min) / span) * (height - 16) - 8,
  }));

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label="Activity history"
      >
        <polyline
          points={coords
            .map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`)
            .join(" ")}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {coords.map((c, index) => (
          <circle
            key={index}
            cx={c.x}
            cy={c.y}
            r={2.5}
            fill="var(--accent)"
            opacity={0.7}
          />
        ))}
      </svg>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="dim mono" style={{ fontSize: "0.72rem" }}>
          {timeAgo(points[0].t)}
        </span>
        <span className="dim mono" style={{ fontSize: "0.72rem" }}>
          {compact(max)} peak
        </span>
        <span className="dim mono" style={{ fontSize: "0.72rem" }}>
          now
        </span>
      </div>
    </div>
  );
}


export default function SignalPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [signal, setSignal] = useState<SignalDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.signal(params.id);
        setSignal(data);
        setSaved(data.is_saved);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Signal not found");
      }
    })();
  }, [params.id]);

  if (error) {
    return (
      <div className="empty">
        <div className="empty-title">Signal unavailable</div>
        <p className="muted">{error}</p>
        <button
          className="btn"
          style={{ marginTop: 14 }}
          onClick={() => router.back()}
        >
          Back
        </button>
      </div>
    );
  }

  if (!signal) return <p className="muted">Loading signal…</p>;

  const status = STATUS_META[signal.status] ?? STATUS_META.NEW;
  const tone = strengthTone(signal.strength);

  const meta: [string, string][] = [
    ["Category", signal.category ?? "—"],
    [
      "Country",
      `${signal.flag ?? "🌐"} ${signal.country_name ?? signal.country_code ?? "Global"}`,
    ],
    ["Source", sourceName(signal.source_id)],
    ["First seen", timeAgo(signal.first_seen_at)],
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
    ["Status", status.label],
    ["Cross-source", String(signal.cross_source_count)],
  ];

  return (
    <>
      <button className="btn btn-sm" onClick={() => router.back()}>
        ← Back
      </button>

      <div className="card" style={{ marginTop: 12 }}>
        <div className="card-top">
          <span className={`badge badge-${status.className}`}>
            {status.emoji} {status.label}
          </span>
          <span className="badge badge-meta">
            {signal.flag ?? "🌐"}{" "}
            {signal.country_name ?? signal.country_code ?? "Global"} ·{" "}
            {sourceName(signal.source_id)}
          </span>
          <span
            className="badge badge-growth"
            data-tone={signal.growth > 0 ? "up" : "down"}
          >
            {formatGrowth(signal.growth)}
          </span>
        </div>

        <h1 style={{ fontSize: "1.2rem", lineHeight: 1.35, margin: "0 0 10px" }}>
          {signal.title}
        </h1>

        {signal.description && (
          <p className="muted" style={{ fontSize: "0.9rem", marginTop: 0 }}>
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

        <div className="card-foot">
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
            className="btn btn-sm btn-primary"
            href={signal.source_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open Original Source
          </a>
          <button
            className="btn btn-sm"
            data-active={saved}
            onClick={async () => {
              if (saved) await api.unsave(signal.id);
              else await api.save(signal.id);
              setSaved(!saved);
            }}
          >
            {saved ? "🔖 Saved" : "🔖 Save"}
          </button>
        </div>
      </div>

      <div className="section-title">HISTORY</div>
      <div className="card">
        <Sparkline
          points={signal.snapshots.map((s) => ({
            t: s.captured_at,
            activity: s.activity,
          }))}
        />
      </div>

      <div className="section-title">DETAILS</div>
      <div className="card">
        <div className="stack">
          {meta.map(([label, value]) => (
            <div className="row" key={label}>
              <span className="dim" style={{ fontSize: "0.8rem", minWidth: 140 }}>
                {label}
              </span>
              <span className="mono" style={{ fontSize: "0.85rem" }}>
                {value}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="section-title">SOURCE INFORMATION</div>
      <div className="card">
        <div className="stack">
          {signal.snapshots.slice(-6).map((s) => (
            <div className="row" key={s.captured_at} style={{ fontSize: "0.8rem" }}>
              <span className="dim mono">{timeAgo(s.captured_at)}</span>
              <span className="mono">
                {formatActivity(s.activity, signal.activity_metric)}
              </span>
              <span
                className="mono"
                style={{
                  color: s.growth > 0 ? "var(--success)" : "var(--text-muted)",
                }}
              >
                {formatGrowth(s.growth)}
              </span>
              <span className="dim mono">strength {Math.round(s.strength)}</span>
            </div>
          ))}
          {signal.snapshots.length === 0 && (
            <p className="dim" style={{ fontSize: "0.82rem" }}>
              No snapshots recorded yet.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
