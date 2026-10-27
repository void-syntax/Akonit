"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export function CommandPaletteModal() {
  const [isOpen, setIsOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        style={{
          position: "fixed",
          bottom: "24px",
          left: "24px",
          zIndex: 9998,
          background: "rgba(9, 9, 11, 0.85)",
          backdropFilter: "blur(12px)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: "8px",
          padding: "8px 12px",
          color: "#a1a1aa",
          fontFamily: "monospace",
          fontSize: "11px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "8px"
        }}
        title="Open Command Palette (Ctrl+K)"
      >
        <span>🔍 Quick Command</span>
        <span style={{ background: "rgba(255,255,255,0.1)", padding: "2px 6px", borderRadius: "4px", fontSize: "10px", color: "#f4f4f5" }}>⌘K</span>
      </button>
    );
  }

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      zIndex: 10000,
      background: "rgba(0,0,0,0.7)",
      backdropFilter: "blur(8px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "16px"
    }}>
      <div style={{
        background: "#09090b",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: "12px",
        width: "100%",
        maxWidth: "500px",
        padding: "16px",
        boxShadow: "0 20px 40px rgba(0,0,0,0.8)",
        fontFamily: "monospace"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "12px" }}>
          <span style={{ color: "#38bdf8", fontWeight: "bold" }}>// COMMAND PALETTE</span>
          <button onClick={() => setIsOpen(false)} style={{ background: "none", border: "none", color: "#a1a1aa", cursor: "pointer", fontSize: "14px" }}>[Esc]</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <button
            onClick={() => { setIsOpen(false); router.push("/"); }}
            style={{ textAlign: "left", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", padding: "10px 12px", borderRadius: "6px", color: "#f4f4f5", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
          >
            <span>⚡ Go to Live Feed & Signals</span>
            <span style={{ color: "#71717a" }}>Home</span>
          </button>
          <button
            onClick={() => { setIsOpen(false); router.push("/radars"); }}
            style={{ textAlign: "left", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", padding: "10px 12px", borderRadius: "6px", color: "#f4f4f5", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
          >
            <span>📡 Manage Intelligence Radars</span>
            <span style={{ color: "#71717a" }}>/radars</span>
          </button>
          <button
            onClick={() => { setIsOpen(false); router.push("/discover"); }}
            style={{ textAlign: "left", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", padding: "10px 12px", borderRadius: "6px", color: "#f4f4f5", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
          >
            <span>🌐 Discover Sources & Feeds</span>
            <span style={{ color: "#71717a" }}>/discover</span>
          </button>
          <button
            onClick={() => { setIsOpen(false); router.push("/settings"); }}
            style={{ textAlign: "left", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", padding: "10px 12px", borderRadius: "6px", color: "#f4f4f5", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
          >
            <span>⚙ System Settings & Telemetry</span>
            <span style={{ color: "#71717a" }}>/settings</span>
          </button>
        </div>
      </div>
    </div>
  );
}
