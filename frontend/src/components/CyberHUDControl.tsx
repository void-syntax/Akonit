"use client";

import { useState } from "react";

export function CyberHUDControl() {
  const [hudActive, setHudActive] = useState(true);
  const [glowMode, setGlowMode] = useState<"cyan" | "emerald" | "violet">("cyan");

  const glowColor = glowMode === "cyan" ? "#38bdf8" : glowMode === "emerald" ? "#10b981" : "#8b5cf6";

  return (
    <div style={{
      position: "fixed",
      bottom: "24px",
      right: "24px",
      zIndex: 9999,
      background: "rgba(9, 9, 11, 0.85)",
      backdropFilter: "blur(12px)",
      border: `1px solid ${glowColor}40`,
      boxShadow: `0 0 20px ${glowColor}20`,
      borderRadius: "12px",
      padding: "12px 16px",
      display: "flex",
      alignItems: "center",
      gap: "12px",
      fontFamily: "monospace",
      fontSize: "11px",
      color: "#f4f4f5"
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: glowColor, boxShadow: `0 0 10px ${glowColor}` }} />
        <span style={{ fontWeight: "bold" }}>HUD: {hudActive ? "ONLINE" : "STANDBY"}</span>
      </div>
      <div style={{ display: "flex", gap: "6px" }}>
        <button
          onClick={() => setGlowMode("cyan")}
          style={{ background: glowMode === "cyan" ? "#38bdf8" : "rgba(255,255,255,0.05)", color: glowMode === "cyan" ? "#000" : "#a1a1aa", border: "none", padding: "4px 8px", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}
        >
          CYAN
        </button>
        <button
          onClick={() => setGlowMode("emerald")}
          style={{ background: glowMode === "emerald" ? "#10b981" : "rgba(255,255,255,0.05)", color: glowMode === "emerald" ? "#000" : "#a1a1aa", border: "none", padding: "4px 8px", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}
        >
          EMERALD
        </button>
        <button
          onClick={() => setGlowMode("violet")}
          style={{ background: glowMode === "violet" ? "#8b5cf6" : "rgba(255,255,255,0.05)", color: glowMode === "violet" ? "#000" : "#a1a1aa", border: "none", padding: "4px 8px", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}
        >
          VIOLET
        </button>
      </div>
      <button
        onClick={() => setHudActive(!hudActive)}
        style={{ background: "transparent", border: `1px solid ${glowColor}`, color: glowColor, padding: "4px 8px", borderRadius: "4px", cursor: "pointer" }}
      >
        {hudActive ? "HIDE" : "SHOW"}
      </button>
    </div>
  );
}
