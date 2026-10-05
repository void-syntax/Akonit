"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SignalCard } from "@/components/SignalCard";
import { api } from "@/lib/api";
import type { Signal } from "@/lib/types";
import { useAuth } from "@/store/auth";

export default function SavedPage() {
  const { email, loading: authLoading } = useAuth();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!email) {
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        setSignals(await api.saved());
      } catch {
        setSignals([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [email]);

  if (authLoading) {
    return <p className="muted">Loading…</p>;
  }

  if (!email) {
    return (
      <div className="empty">
        <div className="empty-title">Cannot reach the local API</div>
        <p className="empty-text">
          Saved signals are stored in your local database. Start the collector
          with <code className="mono">docker compose up</code> and reload.
        </p>
        <button className="btn btn-primary" onClick={() => location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="section-title">Saved signals</div>

      {loading && <p className="muted">Loading…</p>}

      {!loading && signals.length === 0 && (
        <div className="empty">
          <div className="empty-title">Nothing saved yet</div>
          <p className="empty-text">
            Tap the bookmark on any signal to keep it here for later.
          </p>
          <Link className="btn btn-primary" href="/discover">
            Discover signals
          </Link>
        </div>
      )}

      {signals.map((signal) => (
        <SignalCard
          key={signal.id}
          signal={signal}
          onChange={(updated) =>
            setSignals((prev) =>
              updated.is_saved
                ? prev.map((s) => (s.id === updated.id ? updated : s))
                : prev.filter((s) => s.id !== updated.id),
            )
          }
        />
      ))}
    </>
  );
}
