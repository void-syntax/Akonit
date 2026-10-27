"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { TelemetryPulseBadge } from "@/components/TelemetryPulseBadge";

export function StatusBar() {
  const [timeStr, setTimeStr] = useState<string>("");
  const [paused, setPaused] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function update() {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }));
    }
    update();
    const timer = setInterval(update, 30_000);
    
    // Check worker status
    void api.workerStatus().then((res) => {
      setPaused(res.paused);
    }).catch(() => {});

    return () => clearInterval(timer);
  }, []);

  const togglePause = async () => {
    setLoading(true);
    setError(null);
    try {
      if (paused) {
        await api.resumeWorker();
        setPaused(false);
      } else {
        await api.pauseWorker();
        setPaused(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update collection state");
    } finally {
      setLoading(false);
    }
  };

  return (
    <footer className="statusbar" aria-label="Status bar">
      <div className="statusbar-live" data-paused={paused}>
        <span className="statusbar-dot" />
        <span>{paused ? "COLLECTION PAUSED" : "COLLECTION RUNNING"}</span>
        <button
          onClick={() => void togglePause()}
          disabled={loading}
          className="statusbar-toggle"
          title={paused ? "Resume automated background data collection" : "Pause all automated data collection & background searches"}
        >
          {loading ? "Updating…" : paused ? "Resume" : "Pause"}
        </button>
      </div>
      {error && <span className="statusbar-error" role="status">{error}</span>}
      <TelemetryPulseBadge />
      <div className="statusbar-version">
        INTELLIGENCE TERMINAL v2.4 // LAYA AI ENGINE
      </div>
      {timeStr && <time className="statusbar-time" dateTime={new Date().toISOString()}>{timeStr} local</time>}
    </footer>
  );
}
