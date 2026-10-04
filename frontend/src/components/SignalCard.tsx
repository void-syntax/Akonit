"use client";

import Link from "next/link";
import { useState } from "react";

import {
  BoltIcon,
  BookmarkIcon,
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
  firstDetected,
  formatActivity,
  formatGrowth,
  sourceColor,
  sourceName,
  strengthTone,
} from "@/lib/format";
import type { Signal } from "@/lib/types";

interface Props {
  signal: Signal;
  signedIn: boolean;
  onChange?: (updated: Signal) => void;
}

const STATUS_ICON = {
  spark: SparkIcon,
  trending: TrendingUpIcon,
  bolt: BoltIcon,
  pause: PauseIcon,
} as const;

type StatusIconName = keyof typeof STATUS_ICON;

export function SignalCard({ signal, signedIn, onChange }: Props) {
  const [saved, setSaved] = useState(signal.is_saved);
  const [muted, setMuted] = useState(signal.is_ignored);
  const [busy, setBusy] = useState(false);

  const meta = STATUS_META[signal.status] ?? STATUS_META.NEW;
  const StatusIcon = STATUS_ICON[meta.icon as StatusIconName];
  const tone = strengthTone(signal.strength);
  const growthTone = signal.growth > 0 ? "up" : "down";

  async function toggleSave() {
    if (!signedIn) return;
    setBusy(true);
    try {
      if (saved) {
        await api.unsave(signal.id);
        setSaved(false);
      } else {
        await api.save(signal.id);
        setSaved(true);
        onChange?.({ ...signal, is_saved: true });
      }
    } catch {
      /* keep the previous state on failure */
    } finally {
      setBusy(false);
    }
  }

  async function toggleMute() {
    if (!signedIn) return;
    setBusy(true);
    try {
      if (muted) {
        await api.unmute(signal.id);
        setMuted(false);
      } else {
        await api.mute(signal.id);
        setMuted(true);
      }
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card">
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

        <span className="badge badge-growth" data-tone={growthTone}>
          {formatGrowth(signal.growth)}
        </span>
      </div>

      <Link href={`/signals/${signal.id}`}>
        <h3 className="card-title">{signal.title}</h3>
      </Link>

      {signal.description && <p className="card-desc">{signal.description}</p>}

      {signal.keywords.length > 0 && (
        <div className="card-tags">
          {signal.keywords.slice(0, 4).map((tag) => (
            <span key={tag} className="tag-chip">
              {tag.replace(/-/g, " ")}
            </span>
          ))}
          {signal.cross_source_count > 1 && (
            <span className="tag-chip" title="Confirmed across sources">
              <LayersIcon size={11} /> {signal.cross_source_count} sources
            </span>
          )}
        </div>
      )}

      <div className="card-foot">
        <span className="dim text-xs mono">
          {formatActivity(signal.current_activity, signal.activity_metric)} ·{" "}
          {firstDetected(signal.first_seen_at)}
        </span>

        <div className="spacer" />

        <span className="strength" title={`Signal strength ${Math.round(signal.strength)}/100`}>
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
          className="btn btn-sm btn-primary"
          href={signal.source_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open source <ExternalIcon size={13} />
        </a>

        <button
          className="btn btn-sm btn-icon"
          data-active={saved}
          onClick={toggleSave}
          disabled={busy || !signedIn}
          aria-label={saved ? "Remove from saved" : "Save signal"}
          title={signedIn ? (saved ? "Saved" : "Save") : "Sign in to save"}
        >
          <BookmarkIcon size={14} filled={saved} />
        </button>

        <button
          className="btn btn-sm btn-icon"
          data-active={muted}
          onClick={toggleMute}
          disabled={busy || !signedIn}
          aria-label={muted ? "Unmute" : "Hide signal"}
          title={signedIn ? (muted ? "Visible" : "Hide") : "Sign in to hide"}
        >
          {muted ? <PauseIcon size={14} /> : <PauseIcon size={14} />}
        </button>
      </div>
    </article>
  );
}

export function SignalCardSkeleton() {
  return <div className="skeleton" />;
}