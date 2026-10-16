"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SignalCard } from "@/components/SignalCard";
import { EditIcon, TrashIcon } from "@/components/icons";
import { api } from "@/lib/api";
import type { Radar, RadarSummary, Signal } from "@/lib/types";

export default function RadarDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [radar, setRadar] = useState<Radar | null>(null);
  const [summary, setSummary] = useState<RadarSummary | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  // Separate busy states so buttons don't confusingly disable each other.
  const [runBusy, setRunBusy] = useState(false);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runSuccess, setRunSuccess] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, summaryResult, matches] = await Promise.all([
        api.radars(),
        api.radarSummary(params.id),
        api.signals({ radar_id: params.id, limit: 30 }),
      ]);
      setRadar(list.find((r) => r.id === params.id) ?? null);
      setSummary(summaryResult);
      setSignals(matches.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load radar");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function runNow() {
    setRunBusy(true);
    setError(null);
    try {
      await api.runRadar(params.id);
      try {
        await load();
      } catch (loadErr) {
        setError(loadErr instanceof Error ? loadErr.message : "Reload failed after run");
      }
      setRunSuccess(true);
      setTimeout(() => setRunSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setRunBusy(false);
    }
  }

  async function toggleActive() {
    if (!radar) return;
    setToggleBusy(true);
    setError(null);
    try {
      setRadar(await api.updateRadar(radar.id, { is_active: !radar.is_active }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not toggle radar");
    } finally {
      setToggleBusy(false);
    }
  }

  async function remove() {
    if (!radar) return;
    if (!window.confirm(`Delete radar "${radar.name}"?`)) return;
    setRemoveBusy(true);
    setError(null);
    try {
      await api.deleteRadar(radar.id);
      router.push("/radars");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete radar");
    } finally {
      setRemoveBusy(false);
    }
  }

  if (loading) return <p className="muted">Loading radar…</p>;

  if (error && !radar) {
    return (
      <div className="empty" role="status" aria-live="polite">
        <div className="empty-title">Radar unavailable</div>
        <p className="empty-text">{error}</p>
        <Link className="btn" href="/radars">
          Back to radars
        </Link>
      </div>
    );
  }

  if (!radar) return null;

  return (
    <>
      <div className="row" style={{ marginBottom: "var(--s4)" }}>
        <Link className="btn btn-sm btn-ghost" href="/radars">
          ← Radars
        </Link>
        <div className="spacer" />
        <Link className="btn btn-sm" href={`/radars/${radar.id}/edit`}>
          <EditIcon size={14} /> Edit
        </Link>
        <button className="btn btn-sm" onClick={toggleActive} disabled={toggleBusy}>
          {toggleBusy ? "Saving…" : radar.is_active ? "Pause" : "Resume"}
        </button>
        <button className="btn btn-sm" onClick={runNow} disabled={runBusy}>
          {runBusy ? "Running…" : runSuccess ? "Done ✓" : "Run now"}
        </button>
        <button
          className="btn btn-sm btn-danger"
          onClick={remove}
          disabled={removeBusy}
          aria-label="Delete radar"
        >
          {removeBusy ? "…" : <TrashIcon size={14} />}
        </button>
      </div>

      <div className="panel">
        <div className="radar-name" style={{ fontSize: "var(--t-21)" }}>
          <span className="radar-emoji">{radar.emoji ?? "🎯"}</span>
          {radar.name}
        </div>

        {summary && summary.parts.length > 0 && (
          <div className="summary" style={{ marginTop: "var(--s3)" }}>
            {summary.parts.map((part) => (
              <span key={part} className="summary-part">
                {part}
              </span>
            ))}
          </div>
        )}

        <div className="metric-grid" style={{ marginTop: "var(--s4)" }}>
          <div className="metric">
            <div className="metric-label">Active signals</div>
            <div className="metric-value">{radar.active_signal_count}</div>
          </div>
          <div className="metric">
            <div className="metric-label">Total matches</div>
            <div className="metric-value">{radar.match_count}</div>
          </div>
          <div className="metric">
            <div className="metric-label">Threshold</div>
            <div className="metric-value">{Math.round(radar.signal_threshold)}</div>
          </div>
          <div className="metric">
            <div className="metric-label">Notifications</div>
            <div className="metric-value" style={{ fontSize: "var(--t-13)" }}>
              {radar.notification_frequency.replace(/_/g, " ").toLowerCase()}
            </div>
          </div>
        </div>
      </div>

      <div className="section-title">
        Matching signals
        <div className="spacer" />
        <span className="dim text-xs">{signals.length} shown</span>
      </div>

      {error && (
        <div className="alert alert-error" role="alert" aria-live="assertive">
          {error}
        </div>
      )}

      {signals.length === 0 ? (
        <div className="empty" role="status" aria-live="polite">
          <div className="empty-title">No matches yet</div>
          <p className="empty-text">
            The worker checks new signals against this radar every 5 minutes.
            Use &ldquo;Run now&rdquo; to evaluate immediately, or loosen the
            conditions.
          </p>
          <Link className="btn btn-primary" href={`/radars/${radar.id}/edit`}>
            Edit conditions
          </Link>
        </div>
      ) : (
        signals.map((signal) => (
          <SignalCard key={signal.id} signal={signal} />
        ))
      )}
    </>
  );
}
