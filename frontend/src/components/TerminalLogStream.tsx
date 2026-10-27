"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

interface LogItem {
  id: number;
  timestamp: string;
  message: string;
  level: "info" | "success" | "pulse";
}

export function TerminalLogStream() {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(false);
  const [logs, setLogs] = useState<LogItem[]>([]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    let counter = 1;
    try {
      eventSource = new EventSource(`${API_URL}/api/v1/sse/stream`);
      eventSource.onopen = () => {
        setConnected(true);
        setError(false);
      };
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLogs((prev) => [
            {
              id: counter++,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
              message: `Service heartbeat #${data.sequence} received (${data.status}).`,
              level: "pulse",
            },
            ...prev.slice(0, 15),
          ]);
        } catch {}
      };
      eventSource.onerror = () => {
        setConnected(false);
        setError(true);
      };
    } catch {
      setConnected(false);
      setError(true);
    }

    return () => {
      if (eventSource) eventSource.close();
    };
  }, []);

  return (
    <section aria-label="Service connection events" style={{ background: "var(--surface-1)", border: "1px solid var(--line)", borderRadius: "8px", padding: "16px", fontFamily: "monospace", fontSize: "12px", color: "var(--text-2)", margin: "16px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: "8px" }}>
        <span style={{ color: "var(--brand-strong)", fontWeight: "bold", letterSpacing: "0.05em" }}>// SERVICE CONNECTION</span>
        <span role="status" style={{ fontSize: "10px", padding: "2px 6px", background: connected ? "var(--brand-soft)" : "rgba(245, 158, 11, 0.1)", color: connected ? "var(--brand-strong)" : "var(--warn)", borderRadius: "4px" }}>{connected ? "CONNECTED" : error ? "RECONNECTING" : "CONNECTING"}</span>
      </div>
      <div aria-live="polite" style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "150px", overflowY: "auto" }}>
        {logs.length === 0 && <span>Waiting for service heartbeat…</span>}
        {logs.map((log) => (
          <div key={log.id} style={{ display: "flex", gap: "10px" }}>
            <span style={{ color: "#52525b" }}>[{log.timestamp}]</span>
            <span style={{ color: log.level === "success" ? "#10b981" : log.level === "pulse" ? "#38bdf8" : "#d4d4d8" }}>
              {log.message}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
