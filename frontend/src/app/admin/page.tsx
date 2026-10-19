"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface AdminStats {
  total_signals: number;
  active_websocket_connections: number;
  dlq_size: number;
  cache_hits: number;
  cache_misses: number;
  service: string;
  status: string;
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.adminStats();
      setStats(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin stats");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchStats();
    const interval = setInterval(() => {
      void fetchStats();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "24px 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 4 }}>Admin & Observability Dashboard</h1>
          <p className="muted text-sm">Real-time system telemetry and key Prometheus metrics summary.</p>
        </div>
        <button
          onClick={() => void fetchStats()}
          style={{
            padding: "8px 16px",
            borderRadius: 6,
            background: "var(--accent, #3b82f6)",
            color: "#fff",
            border: "none",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          Refresh Metrics
        </button>
      </div>

      {error && (
        <div style={{ padding: 16, background: "rgba(239, 68, 68, 0.1)", border: "1px solid #ef4444", borderRadius: 8, color: "#ef4444", marginBottom: 24 }}>
          {error}
        </div>
      )}

      {loading && !stats ? (
        <div className="muted" style={{ padding: 40, textAlign: "center" }}>Loading metrics...</div>
      ) : stats ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 32 }}>
            <div style={{ background: "var(--card-bg, #1e293b)", padding: 20, borderRadius: 12, border: "1px solid var(--border, #334155)" }}>
              <div className="muted text-sm" style={{ marginBottom: 8 }}>Total Signals Ingested</div>
              <div style={{ fontSize: 32, fontWeight: 700 }}>{stats.total_signals.toLocaleString()}</div>
            </div>

            <div style={{ background: "var(--card-bg, #1e293b)", padding: 20, borderRadius: 12, border: "1px solid var(--border, #334155)" }}>
              <div className="muted text-sm" style={{ marginBottom: 8 }}>Active WebSocket / Streams</div>
              <div style={{ fontSize: 32, fontWeight: 700, color: "#10b981" }}>{stats.active_websocket_connections}</div>
            </div>

            <div style={{ background: "var(--card-bg, #1e293b)", padding: 20, borderRadius: 12, border: "1px solid var(--border, #334155)" }}>
              <div className="muted text-sm" style={{ marginBottom: 8 }}>Dead Letter Queue (DLQ)</div>
              <div style={{ fontSize: 32, fontWeight: 700, color: stats.dlq_size > 0 ? "#f59e0b" : "inherit" }}>{stats.dlq_size}</div>
            </div>

            <div style={{ background: "var(--card-bg, #1e293b)", padding: 20, borderRadius: 12, border: "1px solid var(--border, #334155)" }}>
              <div className="muted text-sm" style={{ marginBottom: 8 }}>Cache Hit / Miss Ratio</div>
              <div style={{ fontSize: 32, fontWeight: 700 }}>
                {stats.cache_hits} / {stats.cache_misses}
              </div>
            </div>
          </div>

          <div style={{ background: "var(--card-bg, #1e293b)", borderRadius: 12, border: "1px solid var(--border, #334155)", overflow: "hidden" }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border, #334155)", fontWeight: 600 }}>
              Prometheus Metrics & Service Health
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
              <tbody>
                <tr style={{ borderBottom: "1px solid var(--border, #334155)" }}>
                  <td style={{ padding: "16px 20px", fontWeight: 500 }}>Service Name</td>
                  <td style={{ padding: "16px 20px" }}>{stats.service}</td>
                </tr>
                <tr style={{ borderBottom: "1px solid var(--border, #334155)" }}>
                  <td style={{ padding: "16px 20px", fontWeight: 500 }}>System Status</td>
                  <td style={{ padding: "16px 20px", color: "#10b981", fontWeight: 600, textTransform: "uppercase" }}>{stats.status}</td>
                </tr>
                <tr style={{ borderBottom: "1px solid var(--border, #334155)" }}>
                  <td style={{ padding: "16px 20px", fontWeight: 500 }}>Prometheus Endpoint</td>
                  <td style={{ padding: "16px 20px" }}>
                    <a href="/metrics" target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent, #3b82f6)", textDecoration: "underline" }}>
                      /metrics (Open Prometheus Format)
                    </a>
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: "16px 20px", fontWeight: 500 }}>Scraped Metrics Monitored</td>
                  <td style={{ padding: "16px 20px" }} className="muted text-sm">
                    signals_ingested_total, signals_noise_filtered_total, laya_classification_duration_seconds, pipeline_cycle_duration_seconds, active_websocket_connections, cache_hits_total, cache_misses_total, dlq_size
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
