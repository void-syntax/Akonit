"use client";

import { useEffect, useState, useRef } from "react";

interface LogItem {
  id: number;
  timestamp: string;
  message: string;
  level: "info" | "success" | "pulse";
}

export function TerminalLogStream() {
  const [mounted, setMounted] = useState(false);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [status, setStatus] = useState<"CONNECTING" | "CONNECTED" | "RECONNECTING">("CONNECTING");

  useEffect(() => {
    setMounted(true);
    const nowStr = new Date().toLocaleTimeString();
    setLogs([
      { id: 1, timestamp: nowStr, message: "Advanced kernel & vector memory cache initialized.", level: "info" },
      { id: 2, timestamp: nowStr, message: "LSH Forest & Nyström attention engines online.", level: "success" },
      { id: 3, timestamp: nowStr, message: "Simulating real-time telemetry pulse stream.", level: "pulse" },
    ]);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const interval = setInterval(() => {
      setStatus("CONNECTED");
      setLogs((prev) => [
        {
          id: Date.now(),
          timestamp: new Date().toLocaleTimeString(),
          message: `Synthetic Telemetry Pulse #${Math.floor(Math.random() * 1000)} received. Status: OK (Vector cache active)`,
          level: "pulse",
        },
        ...prev.slice(0, 15),
      ]);
    }, 4000);

    return () => clearInterval(interval);
  }, [mounted]);

  if (!mounted) {
    return (
      <div style={{ background: "#09090b", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "8px", padding: "16px", fontFamily: "monospace", fontSize: "12px", color: "#a1a1aa", margin: "16px 0", height: "120px" }} />
    );
  }

  return (
    <div style={{ background: "#09090b", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "8px", padding: "16px", fontFamily: "monospace", fontSize: "12px", color: "#a1a1aa", margin: "16px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: "8px" }}>
        <span style={{ color: "#38bdf8", fontWeight: "bold", letterSpacing: "0.05em" }}>// LIVE INTELLIGENCE STREAM & VECTOR CACHE</span>
        <span style={{
          fontSize: "10px",
          padding: "2px 6px",
          background: status === "CONNECTED" ? "rgba(16, 185, 129, 0.1)" : "rgba(234, 179, 8, 0.1)",
          color: status === "CONNECTED" ? "#10b981" : "#eab308",
          borderRadius: "4px"
        }}>
          {status}
        </span>
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
