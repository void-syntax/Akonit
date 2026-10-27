"use client";

import { useEffect, useRef, useState } from "react";

import { api, type FeedQuery } from "./api";
import type { SignalPage } from "./types";

export type LiveState = "connecting" | "live" | "offline";

/**
 * Keeps the feed fresh without a refresh while respecting active filters.
 */
export function useLiveFeed(
  query: FeedQuery,
  onNewSignals: (page: SignalPage) => void,
) {
  const [state, setState] = useState<LiveState>("connecting");
  const queryRef = useRef(query);
  queryRef.current = query;
  const handlerRef = useRef(onNewSignals);
  handlerRef.current = onNewSignals;

  useEffect(() => {
    let active = true;
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let currentInterval = 15_000;

    const poll = async () => {
      try {
        const currentQuery = queryRef.current;
        const page = await api.signals({ ...currentQuery, limit: Math.min(currentQuery.limit ?? 30, 30), offset: 0 });
        if (!active) return;
        setState("live");
        currentInterval = 15_000;
        handlerRef.current(page);
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

    // Poll immediately on query change / mount, then follow interval
    void poll();

    return () => {
      active = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [JSON.stringify(query)]);

  return state;
}
