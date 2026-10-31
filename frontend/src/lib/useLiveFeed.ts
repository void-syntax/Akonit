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
    let requestId = 0;
    let controller: AbortController | null = null;
    let currentInterval = 15_000;

    const poll = async () => {
      if (!active || document.visibilityState === "hidden") return;
      const currentRequestId = ++requestId;
      controller = new AbortController();
      try {
        const currentQuery = queryRef.current;
        const page = await api.signals(
          { ...currentQuery, limit: Math.min(currentQuery.limit ?? 30, 30), offset: 0 },
          { signal: controller.signal },
        );
        if (!active || currentRequestId !== requestId) return;
        setState("live");
        currentInterval = 15_000;
        handlerRef.current(page);
      } catch (err) {
        if (
          active &&
          currentRequestId === requestId &&
          !(err instanceof Error && err.name === "AbortError")
        ) {
          setState("offline");
          currentInterval = Math.min(currentInterval * 1.5, 60_000);
        }
      } finally {
        if (
          active &&
          currentRequestId === requestId &&
          document.visibilityState === "visible"
        ) {
          timerId = setTimeout(() => void poll(), currentInterval);
        }
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        requestId += 1;
        controller?.abort();
        controller = null;
        if (timerId) clearTimeout(timerId);
        timerId = null;
      } else {
        setState("connecting");
        void poll();
      }
    };

    // Poll immediately on query change / mount, then follow interval
    void poll();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      active = false;
      requestId += 1;
      controller?.abort();
      if (timerId) clearTimeout(timerId);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [JSON.stringify(query)]);

  return state;
}
