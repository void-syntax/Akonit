"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";

export function StatusBar() {
  const [timeStr, setTimeStr] = useState<string>("");
  const [paused, setPaused] = useState<boolean>(false);
  const [worker, setWorker] = useState<
    Awaited<ReturnType<typeof api.workerStatus>> | null
  >(null);

  useEffect(() => {
    function update() {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }));
    }
    update();
    const timer = setInterval(update, 30_000);

    let active = true;
    const pollWorker = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const result = await api.workerStatus();
        if (active) {
          setWorker(result);
          setPaused(result.paused);
        }
      } catch {
        if (active) setWorker(null);
      }
    };
    void pollWorker();
    const workerTimer = setInterval(() => void pollWorker(), 15_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void pollWorker();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      active = false;
      clearInterval(timer);
      clearInterval(workerTimer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const stateLabel = paused
    ? "COLLECTION PAUSED"
    : worker === null
      ? "CHECKING COLLECTOR"
      : worker.running
        ? "COLLECTOR ACTIVE"
        : "COLLECTOR OFFLINE";
  const lastResult = worker?.last_collection_result;
  const nextSourceCheck = worker?.next_source_check_at
    ? new Date(worker.next_source_check_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <footer className="statusbar" aria-label="Status bar">
      <div
        className="statusbar-live"
        data-paused={paused}
        data-offline={worker !== null && !worker.running}
        aria-live="polite"
      >
        <span className="statusbar-dot" />
        <span>{stateLabel}</span>
        <Link href="/profile" className="statusbar-manage">Manage</Link>
      </div>
      {worker?.running && lastResult && (
        <span className="statusbar-note" title="The collector stays active and checks each source on its own schedule to respect source limits.">
          {nextSourceCheck ? `Next source check ~${nextSourceCheck} · ` : ""}
          {(lastResult.sources_due ?? 0) === 0
            ? "Waiting for the next scheduled source check"
            : `Last pass: ${lastResult.sources_due} due · ${lastResult.signals_created ?? 0} new`}
        </span>
      )}
      {worker !== null && !worker.running && !paused && (
        <span className="statusbar-error" role="status">
          Start the app again to restart the background collector.
        </span>
      )}
      <div className="statusbar-version">
        INTELLIGENCE TERMINAL v2.4 // LAYA AI ENGINE
      </div>
      {timeStr && <time className="statusbar-time" dateTime={new Date().toISOString()}>{timeStr} local</time>}
    </footer>
  );
}
