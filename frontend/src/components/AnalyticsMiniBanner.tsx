"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function AnalyticsMiniBanner() {
  const [metrics, setMetrics] = useState<{
    signals?: { total?: number };
    sources?: { active_24h?: number };
    database?: { status?: string; page_count?: number; freelist_count?: number };
  } | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const result = await api.telemetryMetrics();
        if (active) setMetrics(result);
      } catch {
        // Retain the last good values while the API is temporarily unavailable.
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 60_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  if (!metrics) return null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px", margin: "16px 0" }}>
      <div style={{ background: "var(--surface-1)", border: "1px solid var(--line)", borderRadius: "8px", padding: "12px" }}>
        <div style={{ fontSize: "11px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Signals in database</div>
        <div style={{ fontSize: "16px", fontWeight: "bold", color: "#f4f4f5", marginTop: "4px" }}>
          {(metrics.signals?.total ?? 0).toLocaleString()} tracked
        </div>
      </div>
      <div style={{ background: "var(--surface-1)", border: "1px solid var(--line)", borderRadius: "8px", padding: "12px" }}>
        <div style={{ fontSize: "11px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Sources active (24h)</div>
        <div style={{ fontSize: "16px", fontWeight: "bold", color: "#f4f4f5", marginTop: "4px" }}>
          {metrics.sources?.active_24h ?? 0} reporting
        </div>
      </div>
      <div style={{ background: "var(--surface-1)", border: "1px solid var(--line)", borderRadius: "8px", padding: "12px" }}>
        <div style={{ fontSize: "11px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Database storage</div>
        <div style={{ fontSize: "16px", fontWeight: "bold", color: "#10b981", marginTop: "4px" }}>
          {metrics.database?.status === "healthy" ? "SQLite healthy" : "Available"}
        </div>
        <div style={{ color: "var(--text-3)", fontSize: "11px", marginTop: "3px" }}>
          {metrics.database?.page_count != null ? `${metrics.database.page_count.toLocaleString()} pages` : "Storage details unavailable"}
        </div>
      </div>
    </div>
  );
}
