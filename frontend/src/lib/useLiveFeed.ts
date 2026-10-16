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
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let currentInterval = 15_000;

    const poll = async () => {
      try {
        const page = await api.signals({ tab: "all", limit: 5 });
        if (!active) return;
        setState("live");
        currentInterval = 15_000;
        const newest = page.items[0];
        if (newest) handlerRef.current(newest);
      } catch {
        if (active) {
          setState("offline");
          currentInterval = Math.min(currentInterval * 1.5, 60_000);
        }
      } finally {
        if (active) {
          timerId = setTimeout(() => void poll(), currentInterval);
        }
      }
    };

    void poll();

    return () => {
      active = false;
      if (timerId) clearTimeout(timerId);
    };
  }, []);

  return state;
}