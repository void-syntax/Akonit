"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PlusIcon } from "@/components/icons";
import { api } from "@/lib/api";
import type { Radar, RadarSummary } from "@/lib/types";
import { useAuth } from "@/store/auth";

export default function RadarsPage() {
  const { email, loading: authLoading } = useAuth();
  const [radars, setRadars] = useState<Radar[]>([]);
  const [summaries, setSummaries] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!email) {
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const list = await api.radars();
        setRadars(list);
        const entries = await Promise.all(
          list.map(async (radar) => {
            try {
              const summary: RadarSummary = await api.radarSummary(radar.id);
              return [radar.id, summary.parts] as const;
            } catch {
              return [radar.id, []] as const;
            }
          }),
        );
        setSummaries(Object.fromEntries(entries));
      } catch {
        setRadars([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [email]);

  if (authLoading) return <p className="muted">Loading…</p>;

  if (!email) {
    return (
      <div className="empty">
        <div className="empty-title">Cannot reach the local API</div>
        <p className="empty-text">
          Radars need the collector running. Start it with{" "}
          <code className="mono">docker compose up</code> and reload this page.
        </p>
        <button className="btn btn-primary" onClick={() => location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="section-title">
        My radars
        <div className="spacer" />
        <span className="dim text-xs">{radars.length} configured</span>
      </div>

      {loading && <p className="muted">Loading radars…</p>}

      {!loading && radars.length === 0 && (
        <div className="empty">
          <div className="empty-title">No radars yet</div>
          <p className="empty-text">
            Create your first radar: pick countries, sources, tags and a growth
            threshold. It starts monitoring immediately.
          </p>
          <Link className="btn btn-primary" href="/radars/new">
            <PlusIcon size={15} /> Create your first radar
          </Link>
        </div>
      )}

      {radars.length > 0 && (
        <div className="radar-grid">
          {radars.map((radar) => {
            const parts = summaries[radar.id] ?? [];
            return (
              <div key={radar.id} className="radar-card" data-active={radar.is_active}>
                <div className="radar-name">
                  <span className="radar-emoji">{radar.emoji ?? "🎯"}</span>
                  {radar.name}
                </div>

                <div className="radar-summary">
                  {parts.length > 0 ? (
                    parts.map((part, index) => (
                      <span key={part}>
                        {index > 0 && (
                          <span className="radar-summary-part"> {" + "} </span>
                        )}
                        <span className="summary-part">{part}</span>
                      </span>
                    ))
                  ) : (
                    <span className="dim">Conditions loading…</span>
                  )}
                </div>

                <div className="radar-stats">
                  <span className="radar-count">{radar.active_signal_count}</span>
                  <span className="radar-count-label">active signals</span>
                  <div className="spacer" />
                  <span className="dim text-xs">
                    {radar.notification_frequency.replace(/_/g, " ").toLowerCase()}
                  </span>
                </div>

                <div className="row">
                  <Link className="btn btn-sm" href={`/radars/${radar.id}`}>
                    Open
                  </Link>
                  <Link className="btn btn-sm btn-ghost" href={`/radars/${radar.id}/edit`}>
                    Edit
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {radars.length > 0 && (
        <div style={{ marginTop: "var(--s5)" }}>
          <Link className="btn btn-primary" href="/radars/new">
            <PlusIcon size={15} /> Create radar
          </Link>
        </div>
      )}
    </>
  );
}
