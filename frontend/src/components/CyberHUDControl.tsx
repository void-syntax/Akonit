"use client";

import { useEffect, useState } from "react";

type Accent = "lime" | "cyan" | "violet";
const ACCENTS: Record<Accent, { brand: string; strong: string; soft: string; line: string }> = {
  lime: { brand: "#a6d66f", strong: "#c2e79b", soft: "rgba(166,214,111,.11)", line: "rgba(166,214,111,.32)" },
  cyan: { brand: "#38bdf8", strong: "#7dd3fc", soft: "rgba(56,189,248,.11)", line: "rgba(56,189,248,.32)" },
  violet: { brand: "#a78bfa", strong: "#c4b5fd", soft: "rgba(167,139,250,.11)", line: "rgba(167,139,250,.32)" },
};

export function CyberHUDControl() {
  const [accent, setAccent] = useState<Accent>("lime");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem("signal-radar-accent") as Accent | null;
    if (saved && saved in ACCENTS) setAccent(saved);
    setVisible(true);
  }, []);

  useEffect(() => {
    if (!visible) return;
    const colors = ACCENTS[accent];
    const root = document.documentElement;
    root.style.setProperty("--brand", colors.brand);
    root.style.setProperty("--brand-strong", colors.strong);
    root.style.setProperty("--brand-soft", colors.soft);
    root.style.setProperty("--brand-line", colors.line);
    root.style.setProperty("--st-new", colors.brand);
    root.style.setProperty("--st-new-bg", colors.soft);
    root.style.setProperty("--st-new-line", colors.line);
    window.localStorage.setItem("signal-radar-accent", accent);
  }, [accent, visible]);

  if (!visible) return null;

  return (
    <section aria-label="Appearance settings" className="hud-control" style={{
      position: "fixed",
      bottom: "40px",
      right: "24px",
      zIndex: 60,
      background: "var(--surface-1)",
      border: "1px solid var(--line)",
      borderRadius: "12px",
      padding: "8px 10px",
      display: "flex",
      alignItems: "center",
      gap: "8px",
      fontSize: "11px",
      color: "var(--text-2)"
    }}>
      <span>Акцент</span>
      {(["lime", "cyan", "violet"] as const).map((color) => (
        <button key={color} type="button" aria-label={`Цвет акцента: ${color}`} aria-pressed={accent === color}
          onClick={() => setAccent(color)}
          style={{ width: 24, height: 24, borderRadius: "50%", border: accent === color ? "2px solid var(--text-1)" : "1px solid var(--line-strong)", background: ACCENTS[color].brand }} />
      ))}
    </section>
  );
}
