"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL } from "./api";
import type { Signal } from "./types";

interface LiveEvent {
  type: "hello" | "signal" | "ping";
  signal?: Signal;
  signals?: Signal[];
}

export type LiveState = "connecting" | "live" | "offline";

/**
 * Subscribes to the SSE feed so the UI updates without a refresh.
 * Falls back to nothing (the feed still polls on mount).
 */
export function useLiveFeed(onSignal: (signal: Signal) => void) {
  const [state, setState] = useState<LiveState>("connecting");
  const handlerRef = useRef(onSignal);
  handlerRef.current = onSignal;

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      if (closed) return;
      setState("connecting");
      source = new EventSource(`${API_URL}/api/v1/stream/feed`);

      source.onopen = () => setState("live");

      source.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as LiveEvent;
          if (payload.type === "signal" && payload.signal) {
            handlerRef.current(payload.signal);
          }
          setState("live");
        } catch {
          /* ignore malformed frames */
        }
      };

      source.onerror = () => {
        source?.close();
        setState("offline");
        // Auto-reconnect: the feed must survive a backend restart.
        retry = setTimeout(connect, 5000);
      };
    };

    connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      source?.close();
    };
  }, []);

  return state;
}