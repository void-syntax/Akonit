"use client";

import { useEffect, useRef, useState } from "react";

import { api, type FeedQuery } from "./api";
import type { Signal } from "./types";

export type LiveState = "connecting" | "live" | "offline";

/**
 * Keeps the feed fresh without a refresh while respecting active filters.
 */
export function useLiveFeed(
  query: FeedQuery,
  onNewSignals: (signals: Signal[]) => void,
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
        const page = await api.signals(queryRef.current);
        if (!active) return;
        setState("live");
        currentInterval = 15_000;
        if (page.items.length > 0) {
          handlerRef.current(page.items);
        }
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

    timerId = setTimeout(() => void poll(), currentInterval);

    return () => {
      active = false;
      if (timerId) clearTimeout(timerId);
    };
  }, []);

  return state;
}
