"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import type { Signal } from "./types";

export type LiveState = "connecting" | "live" | "offline";

const POLL_MS = 20_000;

/**
 * Keeps the feed fresh without a refresh.
 *
 * There is no server-sent-events endpoint on the edge deployment, so this polls
 * the feed endpoint instead. Polling is honest about failure: a failed request
 * reports `offline`, whereas a successful one reports `live` even when the
 * database is still empty. An EventSource that 404s would have reported the
 * opposite and looked like an outage.
 */
export function useLiveFeed(onSignal: (signal: Signal) => void) {
  const [state, setState] = useState<LiveState>("connecting");
  const handlerRef = useRef(onSignal);
  handlerRef.current = onSignal;

  useEffect(() => {
    let active = true;
    let timerId: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const page = await api.signals({ tab: "all", limit: 5 });
        if (!active) return;
        setState("live");
        // Only the newest row can be new since the last poll, so the rest of
        // the feed is refreshed by the page's own load() instead.
        const newest = page.items[0];
        if (newest) handlerRef.current(newest);
      } catch {
        if (active) setState("offline");
      }
    };

    void poll();
    timerId = setInterval(() => void poll(), POLL_MS);

    return () => {
      active = false;
      if (timerId) clearInterval(timerId);
    };
  }, []);

  return state;
}