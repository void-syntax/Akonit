"use client";

import { create } from "zustand";

import { api } from "@/lib/api";

interface AuthState {
  email: string | null;
  loading: boolean;
  error: string | null;
  hydrate: () => Promise<void>;
}

/**
 * Local mode: there is no login.
 *
 * The API resolves a single local account, so asking who we are is enough to
 * learn that personalised features (radars, saved signals, notifications) are
 * available. Keeping a store here instead of hardcoding "signed in" means the
 * UI still degrades honestly if the API is unreachable.
 */
export const useAuth = create<AuthState>((set, get) => ({
  email: null,
  loading: true,
  error: null,

  hydrate: async () => {
    // Deduplicate concurrent hydrate calls: if already resolved, skip.
    if (!get().loading && get().email !== null) return;
    try {
      const user = await api.me();
      set({ email: user.email, loading: false, error: null });
    } catch (err) {
      set({
        email: null,
        loading: false,
        error: err instanceof Error ? err.message : "Could not resolve local account",
      });
    }
  },
}));

/** True when the local account resolved; every write feature needs it. */
export function useIsSignedIn(): boolean {
  return useAuth((s) => Boolean(s.email));
}