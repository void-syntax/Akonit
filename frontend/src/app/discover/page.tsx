"use client";

import { useEffect, useState } from "react";

import { FilterSelect } from "@/components/FilterSelect";
import { SignalCard, SignalCardSkeleton } from "@/components/SignalCard";
import { api } from "@/lib/api";
import { countryName, sourceName } from "@/lib/format";
import type { Country, Signal, SourceInfo } from "@/lib/types";

export default function DiscoverPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [country, setCountry] = useState<string[]>([]);
  const [source, setSource] = useState<string[]>([]);
  const [minStrength, setMinStrength] = useState(0);
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);

  useEffect(() => {
    void (async () => {
      try {
        const [c, s] = await Promise.all([
          api.countries(undefined, true),
          api.sources(),
        ]);
        setCountries(c);
        setSources(s.filter((item) => item.status === "ACTIVE"));
      } catch {
        /* filters stay optional */
      }
    })();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const result = await api.discover(
          {
            limit: 40,
            country: country.length ? country : undefined,
            source: source.length ? source : undefined,
            min_strength: minStrength > 0 ? minStrength : undefined,
          },
          { signal: controller.signal },
        );
        setSignals(result.items);
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        setSignals([]);
        setError(err instanceof Error ? err.message : "Could not load discovery");
      } finally {
        setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [country, source, minStrength]);

  return (
    <>
      <div className="section-title">Discover</div>
      <p className="muted text-sm" style={{ marginTop: -4, marginBottom: 16 }}>
        The strongest NEW, RISING and BREAKOUT signals right now &mdash;
        independent of your radars. Notifications still require a radar.
      </p>

      <div className="filters">
        <FilterSelect
          label="Country"
          value={country}
          onChange={setCountry}
          options={countries.map((c) => ({
            value: c.code,
            label: `${c.flag} ${countryName(c.code)}`,
          }))}
          allLabel="All countries"
        />

        <FilterSelect
          label="Source"
          value={source}
          onChange={setSource}
          options={sources.map((s) => ({
            value: s.id,
            label: sourceName(s.id),
          }))}
          allLabel="All sources"
        />

        <button
          className="filter"
          data-active={minStrength >= 50}
          onClick={() => setMinStrength(minStrength >= 50 ? 0 : 50)}
        >
          <span className="filter-label">Strength</span>
          {minStrength >= 50 ? "≥ 50" : "Any"}
        </button>

        {(country.length > 0 || source.length > 0 || minStrength > 0) && (
          <button
            className="filter"
            onClick={() => {
              setCountry([]);
              setSource([]);
              setMinStrength(0);
            }}
          >
            Clear
          </button>
        )}
      </div>

      {error && <div className="alert alert-error" role="alert" aria-live="assertive">{error}</div>}

      {loading && signals.length === 0 && (
        <>
          <SignalCardSkeleton />
          <SignalCardSkeleton />
          <SignalCardSkeleton />
        </>
      )}

      {!loading && signals.length === 0 && (
        <div className="empty" role="status" aria-live="polite">
          <div className="empty-title">Nothing is rising yet</div>
          <p className="empty-text">
            Discovery shows only NEW, RISING and BREAKOUT signals. Check back
            after the next collection cycle.
          </p>
        </div>
      )}

      {signals.map((signal) => (
        <SignalCard
          key={signal.id}
          signal={signal}
        />
      ))}
    </>
  );
}
