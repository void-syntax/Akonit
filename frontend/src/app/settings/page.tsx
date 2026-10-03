"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { sourceName } from "@/lib/format";
import type { SourceHealthReport } from "@/lib/types";

const STATUS_ICON: Record<string, string> = {
  ACTIVE: "🟢",
  DEGRADED: "🟡",
  OFFLINE: "🔴",
  OPTIONAL_CREDENTIALS: "⚪",
};

const STATUS_TEXT: Record<string, string> = {
  ACTIVE: "ACTIVE",
  DEGRADED: "DEGRADED",
  OFFLINE: "OFFLINE",
  OPTIONAL_CREDENTIALS: "OPTIONAL CREDENTIALS",
};

export default function SettingsPage() {
  const [report, setReport] = useState<SourceHealthReport | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setReport(await api.sourceHealth());
      } catch {
        setReport(null);
      }
    })();
  }, []);

  async function collectNow() {
    setCollecting(true);
    setResult(null);
    try {
      const res = await api.collectNow();
      setResult(
        `Fetched ${res.fetched} events · ${res.signals_created} new signals · ${res.sources_ok} sources ok`,
      );
      setReport(await api.sourceHealth());
    } catch (err) {
      setResult(err instanceof Error ? err.message : "Collection failed");
    } finally {
      setCollecting(false);
    }
  }

  return (
    <>
      <div className="section-title">SOURCE HEALTH</div>

      {report && (
        <div className="row" style={{ marginBottom: 12 }}>
          {Object.entries(report.summary).map(([status, count]) => (
            <span key={status} className="badge badge-meta">
              {STATUS_ICON[status]} {STATUS_TEXT[status]}: {count}
            </span>
          ))}
        </div>
      )}

      {!report && <p className="muted">Loading source status…</p>}

      {report?.sources.map((source) => (
        <div key={source.id} className="card">
          <div className="card-top">
            <span
              className={`badge badge-status-${
                source.status === "ACTIVE"
                  ? "rising"
                  : source.status === "OFFLINE"
                    ? "breakout"
                    : source.status === "DEGRADED"
                      ? "new"
                      : "fading"
              }`}
            >
              {STATUS_ICON[source.status]} {STATUS_TEXT[source.status]}
            </span>
            <span className="badge badge-meta">{source.name}</span>
            <span className="badge badge-meta">{source.cost}</span>
          </div>

          <h3 className="card-title" style={{ WebkitLineClamp: 3 }}>
            {source.description ?? sourceName(source.id)}
          </h3>

          <div className="card-foot">
            <span className="dim mono" style={{ fontSize: "0.73rem" }}>
              strategy: {source.strategy ?? "—"} · records:{" "}
              {source.total_records} · failures: {source.consecutive_failures}
            </span>
          </div>

          {source.status_reason && (
            <p className="dim" style={{ fontSize: "0.76rem", marginBottom: 0 }}>
              {source.status_reason}
            </p>
          )}
          {source.last_error && (
            <p className="error" style={{ marginTop: 8, marginBottom: 0 }}>
              {source.last_error.slice(0, 220)}
            </p>
          )}
        </div>
      ))}

      <div className="section-title">PIPELINE</div>
      <div className="row">
        <button className="btn" onClick={collectNow} disabled={collecting}>
          {collecting ? "Collecting…" : "Run collection now"}
        </button>
        <span className="muted" style={{ fontSize: "0.82rem" }}>
          {result ?? "The worker runs this automatically every 15 minutes."}
        </span>
      </div>

      <div className="section-title">PRINCIPLE</div>
      <p className="muted" style={{ fontSize: "0.86rem" }}>
        You decide what to watch. Signal Radar watches it 24/7 and shows you what
        only just started to grow — not what everyone already saw.
      </p>
      <p className="dim" style={{ fontSize: "0.8rem" }}>
        Zero API cost. No LLM. All detection is deterministic: growth,
        acceleration, recency, persistence and cross-source confirmation.
      </p>
    </>
  );
}