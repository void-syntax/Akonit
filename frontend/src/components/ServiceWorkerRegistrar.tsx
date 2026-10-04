"use client";

import { useEffect } from "react";

/**
 * Registers the push service worker.
 *
 * Without this `navigator.serviceWorker.ready` never resolves, so enabling
 * browser push would hang forever instead of failing with a clear message.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    const register = async () => {
      try {
        await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      } catch (error) {
        console.error("service worker registration failed", error);
      }
    };

    void register();
  }, []);

  return null;
}