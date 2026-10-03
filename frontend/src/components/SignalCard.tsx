"use client";

import Link from "next/link";
import { useState } from "react";

import { api } from "@/lib/api";
import {
  STATUS_META,
  formatActivity,
  formatGrowth,
  sourceName,
  strengthTone,
  timeAgo,
} from "@/lib/format";
import type { Signal } from "@/lib/types";

interface Props {
  signal: Signal;
  onChange?: (updated: Signal) => void;
}

export function SignalCard({ signal, onChange }: Props) {
  const [saved, setSaved] = useState(signal.is_saved);
  const [muted, setMuted] = useState(signal.is_ignored);
  const [busy, setBusy] = useState(false);

  const status = STATUS_META[signal.status] ?? STATUS_META.NEW;
  const tone = strengthTone(signal.strength);
  const growthTone = signal.growth > 0 ? "up" : "down";

  async function toggleSave() {
    setBusy(true);
    try {
      const updated = saved ? await api.unsave(signal.id) : await api.save(signal.id);
      setSaved(!saved);
      if (!saved && updated) onChange?.({ ...signal, is_saved: true });
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  async function toggleMute() {
    setBusy(true);
    try {
      if (muted) await api.unmute(signal.id);
      else await api.mute(signal.id);
      setMuted(!muted);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card">
      <div className="card-top">
        <span className={`badge badge-${status.className}`}>
          {status.emoji} {status.label}
        </span>
        <span className="badge badge-meta">
          {signal.flag ?? "🌐"} {signal.country_name ?? signal.country_code ?? "Global"}
          {" · "}
          {sourceName(signal.source_id)}
        </span>
        <span className="badge badge-growth" data-tone={growthTone}>
          {formatGrowth(signal.growth)}
        </span>
        {signal.cross_source_count > 1 && (
          <span className="badge badge-meta">
            cross-source: {signal.cross_source_count}
          </span>
        )}
      </div>

      <Link href={`/signals/${signal.id}`}>
        <h3 className="card-title">{signal.title}</h3>
      </Link>

      {signal.keywords.length > 0 && (
        <div className="card-tags">
          {signal.keywords.slice(0, 4).map((tag) => (
            <span key={tag} className="tag-chip">
              {tag.replace(/-/g, " ")}
            </span>
          ))}
        </div>
      )}

      <div className="card-foot">
        <span className="dim mono" style={{ fontSize: "0.75rem" }}>
          {formatActivity(signal.current_activity, signal.activity_metric)} ·{" "}
          {timeAgo(signal.first_seen_at)}
        </span>

        <div className="spacer" />

        <span className="strength" title={`Signal strength ${signal.strength}/100`}>
          <span className="strength-bar">
            <span
              className="strength-fill"
              data-tone={tone}
              style={{ width: `${Math.min(signal.strength, 100)}%` }}
            />
          </span>
          {Math.round(signal.strength)}
        </span>

        <a
          className="btn btn-sm"
          href={signal.source_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open
        </a>
        <button
          className="btn btn-sm btn-icon"
          data-active={saved}
          onClick={toggleSave}
          disabled={busy}
          aria-label={saved ? "Remove from saved" : "Save signal"}
        >
          {saved ? "🔖" : "🔖"}
        </button>
        <button
          className="btn btn-sm btn-icon"
          onClick={toggleMute}
          disabled={busy}
          aria-label={muted ? "Unmute signal" : "Hide signal"}
        >
          {muted ? "🔈" : "🔇"}
        </button>
      </div>
    </article>
  );
}