"use client";

import { useCallback, useEffect, useState } from "react";

import { SignalCard } from "@/components/SignalCard";
import { api, type FeedQuery } from "@/lib/api";
import { useLiveFeed } from "@/lib/useLiveFeed";
import { useAuth } from "@/store/auth";
import type { Signal } from "@/lib/types";

const TABS = [
  { id: "all", label: "ALL" },
  { id: "new", label: "NEW" },
  { id: "rising", label: "RISING" },
  { id: "breakout", label: "BREAKOUT" },
  { id: "saved", label: "SAVED" },
] as const;

export default function FeedPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("all");
  const [signals, setSignals] = useState<Signal[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const { email } = useAuth();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const query: FeedQuery = { tab, limit: 40 };
      const page = await api.signals(query);
      setSignals(page.items);
      setTotal(page.total);
    } catch {
      setSignals([]);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void load();
  }, [load]);

  // Live updates: prepend new signals without a refresh.
  const onLiveSignal = useCallback((signal: Signal) => {
    setSignals((prev) => {
      if (prev.some((s) => s.id === signal.id)) return prev;
      return [signal, ...prev].slice(0, 40);
    });
    setTotal((prev) => prev + 1);
  }, []);

  const liveState = useLiveFeed(onLiveSignal);

  if (!email) {
    return (
      <>
        <div className="section-title">SIGNAL RADAR</div>
        <div className="empty">
          <div className="empty-title">Set what you watch once</div>
          <p className="muted" style={{ maxWidth: 380, margin: "0 auto 18px" }}>
            Sign in to start receiving early signals from TikTok, YouTube, X, Reddit,
            Google Trends and more.
          </p>
          <a className="btn btn-primary" href="/login">
            Sign in
          </a>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="section-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span>SIGNAL FEED</span>
        <span className="live" data-state={liveState}>
          <span className="live-dot" />
          {liveState === "live" ? "LIVE" : liveState.toUpperCase()}
        </span>
        <div className="spacer" />
        <span className="dim mono" style={{ fontSize: "0.72rem", textTransform: "none", letterSpacing: 0 }}>
          {total} signals
        </span>
      </div>

      <div className="tabs">
        {TABS.map((item) => (
          <button
            key={item.id}
            className="tab"
            data-active={tab === item.id}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {loading && signals.length === 0 && <p className="muted">Loading signals…</p>}

      {!loading && signals.length === 0 && (
        <div className="empty">
          <div className="empty-title">No signals yet</div>
          <p className="muted">
            Create a radar and the system will monitor 24/7. Signals appear here the
            moment conditions match.
          </p>
          <a className="btn btn-primary" href="/radars" style={{ marginTop: 16 }}>
            Create a Radar
          </a>
        </div>
      )}

      {signals.map((signal) => (
        <SignalCard key={signal.id} signal={signal} />
      ))}
    </>
  );
}