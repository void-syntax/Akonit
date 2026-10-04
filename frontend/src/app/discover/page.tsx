"use client";

import { useEffect, useState } from "react";

import { SignalCard, SignalCardSkeleton } from "@/components/SignalCard";
import { api } from "@/lib/api";
import { countryName, sourceName } from "@/lib/format";
import type { Country, Signal, SourceInfo } from "@/lib/types";
import { useAuth } from "@/store/auth";

export default function DiscoverPage() {
  const { email } = useAuth();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [country, setCountry] = useState("");
  const [source, setSource] = useState("");
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
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.discover({
          limit: 40,
          country: country || undefined,
          source: source || undefined,
        });
        setSignals(result.items);
      } catch (err) {
        setSignals([]);
        setError(err instanceof Error ? err.message : "Could not load discovery");
      } finally {
        setLoading(false);
      }
    })();
  }, [country, source]);

  return (
    <>
      <div className="section-title">Discover</div>
      <p className="muted text-sm" style={{ marginTop: -4, marginBottom: 16 }}>
        The strongest NEW, RISING and BREAKOUT signals right now &mdash;
        independent of your radars. Notifications still require a radar.
      </p>

      <div className="filters">
        <select
          className="filter"
          data-active={Boolean(country)}
          value={country}
          onChange={(e) => setCountry(e.target.value)}
        >
          <option value="">All countries</option>
          {countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.flag} {countryName(c.code)}
            </option>
          ))}
        </select>

        <select
          className="filter"
          data-active={Boolean(source)}
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {sourceName(s.id)}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading && signals.length === 0 && (
        <>
          <SignalCardSkeleton />
          <SignalCardSkeleton />
          <SignalCardSkeleton />
        </>
      )}

      {!loading && signals.length === 0 && (
        <div className="empty">
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
          signedIn={Boolean(email)}
        />
      ))}
    </>
  );
}
