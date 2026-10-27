"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function AnalyticsMiniBanner() {
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    void api.telemetryMetrics().then((res) => {
      setMetrics(res);
    }).catch(() => {});
  }, []);

  if (!metrics) return null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px", margin: "16px 0" }}>
      <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "12px" }}>
        <div style={{ fontSize: "11px", color: "#71717a", textTransform: "uppercase", letterSpacing: "0.05em" }}>Deduplication Engine</div>
        <div style={{ fontSize: "16px", fontWeight: "bold", color: "#f4f4f5", marginTop: "4px" }}>
          {metrics.deduplication?.seen_cache_size ?? 0} items indexed
        </div>
      </div>
      <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "12px" }}>
        <div style={{ fontSize: "11px", color: "#71717a", textTransform: "uppercase", letterSpacing: "0.05em" }}>Story Clusters</div>
        <div style={{ fontSize: "16px", fontWeight: "bold", color: "#f4f4f5", marginTop: "4px" }}>
          {metrics.clustering?.active_clusters ?? 0} active groups
        </div>
      </div>
      <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "12px" }}>
        <div style={{ fontSize: "11px", color: "#71717a", textTransform: "uppercase", letterSpacing: "0.05em" }}>Database Storage</div>
        <div style={{ fontSize: "16px", fontWeight: "bold", color: "#10b981", marginTop: "4px" }}>
          {metrics.database?.wal_mode ? "WAL Optimized" : "Standard"}
        </div>
      </div>
    </div>
  );
}
