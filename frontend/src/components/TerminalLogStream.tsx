"use client";

import { useEffect, useState } from "react";

interface LogItem {
  id: number;
  timestamp: string;
  message: string;
  level: "info" | "success" | "pulse";
}

export function TerminalLogStream() {
  const [logs, setLogs] = useState<LogItem[]>([
    { id: 1, timestamp: new Date().toLocaleTimeString(), message: "Neural attention matrix initialized.", level: "info" },
    { id: 2, timestamp: new Date().toLocaleTimeString(), message: "LSH Forest index active (230 test vectors).", level: "success" },
  ]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    let counter = 3;
    try {
      eventSource = new EventSource("/api/v1/sse/stream");
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLogs((prev) => [
            {
              id: counter++,
              timestamp: new Date().toLocaleTimeString(),
              message: `SSE Telemetry Pulse #${data.sequence} received. Status: ${data.status}`,
              level: "pulse",
            },
            ...prev.slice(0, 15),
          ]);
        } catch {}
      };
    } catch {}

    return () => {
      if (eventSource) eventSource.close();
    };
  }, []);

  return (
    <div style={{ background: "#09090b", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "8px", padding: "16px", fontFamily: "monospace", fontSize: "12px", color: "#a1a1aa", margin: "16px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: "8px" }}>
        <span style={{ color: "#38bdf8", fontWeight: "bold", letterSpacing: "0.05em" }}>// LIVE INTELLIGENCE STREAM & TELEMETRY</span>
        <span style={{ fontSize: "10px", padding: "2px 6px", background: "rgba(16, 185, 129, 0.1)", color: "#10b981", borderRadius: "4px" }}>CONNECTED</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "150px", overflowY: "auto" }}>
        {logs.map((log) => (
          <div key={log.id} style={{ display: "flex", gap: "10px" }}>
            <span style={{ color: "#52525b" }}>[{log.timestamp}]</span>
            <span style={{ color: log.level === "success" ? "#10b981" : log.level === "pulse" ? "#38bdf8" : "#d4d4d8" }}>
              {log.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
