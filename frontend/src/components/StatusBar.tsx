"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function StatusBar() {
  const [timeStr, setTimeStr] = useState<string>("");
  const [paused, setPaused] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    function update() {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    }
    update();
    const timer = setInterval(update, 1000);
    
    // Check worker status
    void api.workerStatus().then((res) => {
      setPaused(res.paused);
    }).catch(() => {});

    return () => clearInterval(timer);
  }, []);

  const togglePause = async () => {
    setLoading(true);
    try {
      if (paused) {
        await api.resumeWorker();
        setPaused(false);
      } else {
        await api.pauseWorker();
        setPaused(true);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <footer className="statusbar" aria-label="Status bar">
      <div className="statusbar-live" style={{ display: "flex", alignItems: "center", gap: "var(--s2)" }}>
        <span className="statusbar-dot" style={{ backgroundColor: paused ? "var(--warn)" : "var(--ok)" }} />
        <span>{paused ? "COLLECTION PAUSED" : "LIVE FEED ACTIVE"}</span>
        <button
          onClick={() => void togglePause()}
          disabled={loading}
          style={{
            background: paused ? "rgba(234, 179, 8, 0.15)" : "rgba(239, 68, 68, 0.15)",
            border: `1px solid ${paused ? "var(--warn)" : "var(--danger)"}`,
            color: paused ? "var(--warn)" : "var(--danger)",
            padding: "2px 8px",
            borderRadius: "4px",
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
            marginLeft: "8px",
          }}
          title={paused ? "Resume automated background data collection" : "Pause all automated data collection & background searches"}
        >
          {loading ? "..." : paused ? "▶ Resume Radar" : "⏹ Pause Radar"}
        </button>
      </div>
      <div className="statusbar-version">
        INTELLIGENCE TERMINAL v2.4 // LAYA AI ENGINE
      </div>
      {timeStr && <div className="statusbar-time">{timeStr} UTC</div>}
    </footer>
  );
}
