"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/store/auth";

export default function LoginPage() {
  const router = useRouter();
  const { email, hydrate, login, register, error, loading } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (email) router.replace("/");
  }, [email, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const ok =
      mode === "login"
        ? await login(form.email, form.password)
        : await register(form.email, form.password);
    setBusy(false);
    if (ok) router.replace("/");
  }

  return (
    <div style={{ paddingTop: 28 }}>
      <div className="section-title">SIGNAL RADAR</div>

      <div className="builder" style={{ maxWidth: 420, margin: "0 auto" }}>
        <h1 style={{ fontSize: "1.25rem", margin: "0 0 4px" }}>
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h1>
        <p className="muted" style={{ fontSize: "0.85rem", margin: "0 0 18px" }}>
          You define the conditions. The system watches the internet 24/7.
        </p>

        <form onSubmit={submit} className="stack">
          <div>
            <label className="field-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="field-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="min 8 characters"
            />
          </div>

          {error && <div className="error">{error}</div>}

          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Sign up"}
          </button>
        </form>

        <button
          className="btn btn-ghost"
          style={{ marginTop: 14, width: "100%" }}
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Need an account? Sign up" : "Have an account? Sign in"}
        </button>

        {!loading && (
          <p className="dim" style={{ fontSize: "0.75rem", marginTop: 16, marginBottom: 0 }}>
            Zero API cost. No credit card. Free public sources only.
          </p>
        )}
      </div>
    </div>
  );
}