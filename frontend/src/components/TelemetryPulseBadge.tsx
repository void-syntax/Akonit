"use client";

import { useEffect, useState } from "react";

export function TelemetryPulseBadge() {
  const [pulseCount, setPulseCount] = useState<number>(0);
  const [connected, setConnected] = useState<boolean>(false);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource("/api/v1/sse/stream");
      eventSource.onopen = () => setConnected(true);
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.sequence) {
            setPulseCount(data.sequence);
          }
        } catch {}
      };
      eventSource.onerror = () => setConnected(false);
    } catch {
      setConnected(false);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, []);

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "11px", fontWeight: 600, color: connected ? "#10b981" : "#f59e0b", padding: "2px 8px", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "4px" }}>
      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: connected ? "#10b981" : "#f59e0b", boxShadow: connected ? "0 0 8px #10b981" : "none" }} />
      <span>SSE PULSE #{pulseCount}</span>
    </div>
  );
}
