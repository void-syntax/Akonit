"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  BoltIcon,
  BookmarkIcon,
  ExternalIcon,
  LayersIcon,
  PauseIcon,
  SparkIcon,
  TrashIcon,
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
  /** Optional: lets the parent reflect a save/mute immediately in its list. */
  onChange?: (updated: Signal) => void;
  /** Optional: lets the parent remove the signal immediately on delete. */
  onDelete?: (id: string) => void;
}

const STATUS_ICON = {
  spark: SparkIcon,
  trending: TrendingUpIcon,
  bolt: BoltIcon,
  pause: PauseIcon,
} as const;

type StatusIconName = keyof typeof STATUS_ICON;

export function SignalCard({ signal, onChange, onDelete }: Props) {
  const [saved, setSaved] = useState(signal.is_saved);
  const [muted, setMuted] = useState(signal.is_ignored);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync local toggle state when the parent refreshes the signal (e.g. from
  // the live feed). Without this, a save/mute triggered elsewhere diverges.
  useEffect(() => {
    setSaved(signal.is_saved);
  }, [signal.is_saved]);
  useEffect(() => {
    setMuted(signal.is_ignored);
  }, [signal.is_ignored]);

  const meta = STATUS_META[signal.status] ?? STATUS_META.NEW;
  const StatusIcon = STATUS_ICON[meta.icon as StatusIconName];
  const tone = strengthTone(signal.strength);
  const growthTone = signal.growth > 0 ? "up" : "down";
  const hasGrowth = signal.growth > 0;

  const isCritical = signal.ai_priority === "critical";
  const isNoise = signal.ai_priority === "noise";

  async function toggleSave() {
    setBusy(true);
    setError(null);
    try {
      if (saved) {
        await api.unsave(signal.id);
        setSaved(false);
        onChange?.({ ...signal, is_saved: false });
      } else {
        await api.save(signal.id);
        setSaved(true);
        onChange?.({ ...signal, is_saved: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update save state");
    } finally {
      setBusy(false);
    }
  }

  async function toggleMute() {
    setBusy(true);
    setError(null);
    try {
      if (muted) {
        await api.unmute(signal.id);
        setMuted(false);
      } else {
        await api.mute(signal.id);
        setMuted(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update mute state");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm("Удалить этот сигнал?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteSignal(signal.id);
      onDelete?.(signal.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить сигнал");
      setBusy(false);
    }
  }

  return (
    <article
      className={`card signal-card ${isCritical ? "signal-card--critical" : ""} ${isNoise ? "signal-card--noise" : ""}`}
      data-status={signal.status}
    >
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

        {signal.ai_category && (
          <span className="ai-badge ai-badge--category">
            {signal.ai_category}
          </span>
        )}

        {signal.ai_priority === "critical" && (
          <span className="ai-badge ai-badge--critical">
            ⚡ Critical
          </span>
        )}

        {signal.ai_priority === "watch" && (
          <span className="ai-badge ai-badge--watch">
            👁 Watch
          </span>
        )}

        {signal.ai_priority === "noise" && (
          <span className="ai-badge ai-badge--noise">
            Noise
          </span>
        )}

        {/* Only claim growth when there was a baseline to grow from. A brand new
            item has nothing to compare against, so showing "+100%" would be a
            lie the engine previously told. */}
        <span className="badge badge-growth" data-tone={hasGrowth ? "up" : "flat"}>
          {hasGrowth ? formatGrowth(signal.growth) : "NEW"}
        </span>

        <div className="spacer" />

        <span className="signal-age" title="How long this has been trending">
          {firstDetected(signal.first_seen_at)}
        </span>
      </div>

      <Link href={`/signals/${signal.id}`} className="signal-card-link">
        <h3 className="card-title">{signal.title}</h3>
      </Link>

      {signal.description && <p className="card-desc">{signal.description}</p>}

      {error && (
        <p className="text-xs" style={{ color: "var(--danger)", marginTop: 8 }} role="alert" aria-live="assertive">
          {error}
        </p>
      )}

      {signal.keywords.length > 0 && (
        <div className="card-tags">
          {signal.keywords.slice(0, 5).map((tag) => (
            <span key={tag} className="tag-chip">
              #{tag.replace(/^custom:/, "").replace(/-/g, " ")}
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
          {formatActivity(signal.current_activity, signal.activity_metric)}
        </span>

        <span
          className="strength"
          title={`Signal strength ${Math.round(signal.strength)}/100`}
        >
          <span className="strength-label">STR</span>
          <span className="strength-bar">
            <span
              className="strength-fill"
              data-tone={tone}
              style={{ width: `${Math.min(signal.strength, 100)}%` }}
            />
          </span>
          <strong>{Math.round(signal.strength)}</strong>
        </span>

        <div className="spacer" />

        {/* The original source is the point of the product, so it is a labelled
            action rather than a small icon nobody notices. */}
        <a
          className="btn btn-sm btn-primary signal-open"
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
          disabled={busy}
          aria-label={saved ? "Remove from saved" : "Save signal"}
          title={saved ? "Saved" : "Save signal"}
        >
          <BookmarkIcon size={14} filled={saved} />
        </button>

        <button
          className="btn btn-sm btn-icon"
          data-active={muted}
          onClick={toggleMute}
          disabled={busy}
          aria-label={muted ? "Unhide signal" : "Hide signal"}
          title={muted ? "Hidden" : "Hide"}
        >
          <PauseIcon size={14} />
        </button>

        <button
          className="btn btn-sm btn-icon btn-icon-danger"
          onClick={handleDelete}
          disabled={busy}
          aria-label="Удалить сигнал"
          title="Удалить сигнал"
        >
          <TrashIcon size={14} />
        </button>
      </div>
    </article>
  );
}

export function SignalCardSkeleton() {
  return <div className="skeleton" />;
}