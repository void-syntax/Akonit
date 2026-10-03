"use client";

import { create } from "zustand";

import { api, setToken } from "@/lib/api";

interface AuthState {
  email: string | null;
  loading: boolean;
  error: string | null;
  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<boolean>;
  register: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  email: null,
  loading: true,
  error: null,

  hydrate: async () => {
    try {
      const user = await api.me();
      set({ email: user.email, loading: false });
    } catch {
      set({ email: null, loading: false });
    }
  },

  login: async (email, password) => {
    set({ error: null });
    try {
      const result = await api.login(email, password);
      setToken(result.access_token);
      set({ email, loading: false });
      return true;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Login failed" });
      return false;
    }
  },

  register: async (email, password) => {
    set({ error: null });
    try {
      const result = await api.register(email, password);
      setToken(result.access_token);
      set({ email, loading: false });
      return true;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Registration failed" });
      return false;
    }
  },

  logout: () => {
    setToken(null);
    set({ email: null });
  },
}));