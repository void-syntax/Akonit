"use client";

import React, { useEffect, useState } from "react";
import { API_URL, ApiError } from "@/lib/api";
import type { IntelligenceBriefing } from "@/lib/types";

interface SignalBriefingProps {
  signalId: string;
  isCriticalOrUnicorn: boolean;
}

export function SignalBriefing({ signalId, isCriticalOrUnicorn }: SignalBriefingProps) {
  const [briefing, setBriefing] = useState<IntelligenceBriefing | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function fetchBriefing() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`${API_URL}/api/v1/signals/${signalId}/briefing`);
        if (!res.ok) {
          if (res.status === 404) {
            setBriefing(null);
            return;
          }
          throw new Error(`Failed to load intelligence briefing (${res.status})`);
        }
        const data = await res.json();
        if (mounted) {
          setBriefing(data);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load briefing");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }
    fetchBriefing();
    return () => {
      mounted = false;
    };
  }, [signalId]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-cyan-500/20 bg-cyan-950/10 p-6 backdrop-blur-xl animate-pulse">
        <div className="h-6 w-48 bg-cyan-500/20 rounded mb-4" />
        <div className="space-y-3">
          <div className="h-4 bg-cyan-500/10 rounded w-full" />
          <div className="h-4 bg-cyan-500/10 rounded w-5/6" />
          <div className="h-4 bg-cyan-500/10 rounded w-4/6" />
        </div>
      </div>
    );
  }

  if (!briefing) {
    if (!isCriticalOrUnicorn) return null;
    return (
      <div className="rounded-2xl border border-dashed border-cyan-500/30 bg-cyan-950/5 p-6 text-center">
        <div className="text-cyan-400 font-mono text-sm mb-2">⚡ Autonomous Intelligence Synthesis Available</div>
        <p className="text-xs text-slate-400 mb-4">This signal qualifies for an Executive Deep Intelligence Briefing (Core Thesis, Alpha, Monetization, Risk).</p>
        <button
          onClick={async () => {
            try {
              setLoading(true);
              const res = await fetch(`${API_URL}/api/v1/signals/${signalId}/briefing`);
              if (res.ok) {
                const data = await res.json();
                setBriefing(data);
              }
            } catch (e) {
              setError("Synthesis failed");
            } finally {
              setLoading(false);
            }
          }}
          className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 rounded-xl font-mono text-xs border border-cyan-500/40 transition-all shadow-lg shadow-cyan-500/10 cursor-pointer"
        >
          Generate Deep Briefing Now
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-cyan-500/30 bg-gradient-to-b from-cyan-950/20 to-slate-950/80 p-6 backdrop-blur-2xl shadow-2xl shadow-cyan-950/40 relative overflow-hidden">
      <div className="absolute top-0 right-0 px-3 py-1 bg-cyan-500/10 border-b border-l border-cyan-500/20 rounded-bl-xl text-[10px] font-mono text-cyan-400 tracking-wider">
        FRANKENSTEIN SYNTHESIS // {briefing.model_used}
      </div>

      <div className="flex items-center gap-2 mb-4">
        <span className="flex h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
        <h3 className="text-base font-bold text-cyan-200 tracking-tight font-mono">
          Executive Intelligence Briefing
        </h3>
        <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
          Confidence: {(briefing.confidence_score * 100).toFixed(0)}%
        </span>
      </div>

      <div className="space-y-5 text-sm">
        {/* Core Thesis */}
        <div className="space-y-1.5">
          <div className="text-xs font-mono font-semibold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
            <span>🎯</span> Core Thesis
          </div>
          <p className="text-slate-300 leading-relaxed text-xs sm:text-sm bg-slate-900/60 p-3.5 rounded-xl border border-slate-800/80">
            {briefing.core_thesis}
          </p>
        </div>

        {/* Alpha Potential */}
        <div className="space-y-1.5">
          <div className="text-xs font-mono font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
            <span>📈</span> Alpha Potential
          </div>
          <p className="text-slate-300 leading-relaxed text-xs sm:text-sm bg-slate-900/60 p-3.5 rounded-xl border border-slate-800/80">
            {briefing.alpha_potential}
          </p>
        </div>

        {/* Monetization Strategy */}
        <div className="space-y-1.5">
          <div className="text-xs font-mono font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
            <span>💰</span> Monetization Strategy
          </div>
          <div className="text-slate-300 leading-relaxed text-xs sm:text-sm bg-slate-900/60 p-3.5 rounded-xl border border-slate-800/80 whitespace-pre-line">
            {briefing.monetization_strategy}
          </div>
        </div>

        {/* Risk Analysis */}
        <div className="space-y-1.5">
          <div className="text-xs font-mono font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
            <span>🛡️</span> Risk Analysis
          </div>
          <div className="text-slate-300 leading-relaxed text-xs sm:text-sm bg-slate-900/60 p-3.5 rounded-xl border border-slate-800/80 whitespace-pre-line">
            {briefing.risk_analysis}
          </div>
        </div>

        {/* Sources Synthesized */}
        {briefing.sources_synthesized && briefing.sources_synthesized.length > 0 && (
          <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Synthesized Corridors:</span>
            {briefing.sources_synthesized.map((src, idx) => (
              <span
                key={idx}
                className="text-[10px] font-mono bg-slate-900 text-slate-300 px-2 py-0.5 rounded border border-slate-800 truncate max-w-[200px]"
                title={src}
              >
                {src}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
