"use client";

import { useEffect, useState } from "react";

import { SignalCard } from "@/components/SignalCard";
import { api } from "@/lib/api";
import type { Signal } from "@/lib/types";

export default function SavedPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        setSignals(await api.saved());
      } catch {
        setSignals([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <>
      <div className="section-title">SAVED SIGNALS</div>

      {loading && <p className="muted">Loading…</p>}

      {!loading && signals.length === 0 && (
        <div className="empty">
          <div className="empty-title">Nothing saved yet</div>
          <p className="muted">
            Tap the bookmark on any signal card to keep it here for later.
          </p>
        </div>
      )}

      {signals.map((signal) => (
        <SignalCard
          key={signal.id}
          signal={signal}
          onChange={(updated) =>
            setSignals((prev) =>
              prev.map((s) => (s.id === updated.id ? updated : s)),
            )
          }
        />
      ))}
    </>
  );
}