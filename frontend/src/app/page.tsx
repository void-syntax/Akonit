"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { SignalCard, SignalCardSkeleton } from "@/components/SignalCard";
import { api, type FeedQuery } from "@/lib/api";
import { countryName, sourceName } from "@/lib/format";
import type { Country, PublicStats, Radar, Signal } from "@/lib/types";
import { useLiveFeed } from "@/lib/useLiveFeed";
import { useAuth } from "@/store/auth";

const TABS = [
  { id: "all", label: "ALL" },
  { id: "rising", label: "RISING" },
  { id: "breakout", label: "BREAKOUT" },
  { id: "new", label: "NEW" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const STEPS = [
  {
    title: "You define conditions",
    text: "Pick countries, sources, tags and thresholds. No code, no SQL.",
  },
  {
    title: "The system watches 24/7",
    text: "15 free sources collected continuously, with full history kept.",
  },
  {
    title: "Signals appear early",
    text: "You get the ones that just started to grow, not what everyone saw.",
  },
  {
    title: "You get notified",
    text: "Browser push or Telegram, the moment your radar matches.",
  },
];

export default function FeedPage() {
  const { email } = useAuth();
  const [tab, setTab] = useState<TabId>("all");
  const [signals, setSignals] = useState<Signal[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [stats, setStats] = useState<PublicStats | null>(null);
  const [radars, setRadars] = useState<Radar[]>([]);
  const [radarFilter, setRadarFilter] = useState<string | null>(null);
  const [countryFilter, setCountryFilter] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [minStrength, setMinStrength] = useState(0);
  const [countries, setCountries] = useState<Country[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query: FeedQuery = { tab, limit: 30 };
      if (radarFilter) query.radar_id = radarFilter;
      if (countryFilter) query.country = [countryFilter];
      if (sourceFilter) query.source = [sourceFilter];
      if (minStrength > 0) query.min_strength = minStrength;

      const page = await api.signals(query);
      setSignals(page.items);
      setTotal(page.total);
    } catch (err) {
      setSignals([]);
      setError(err instanceof Error ? err.message : "Could not load signals");
    } finally {
      setLoading(false);
    }
  }, [tab, radarFilter, countryFilter, sourceFilter, minStrength]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void (async () => {
      try {
        setStats(await api.stats());
      } catch {
        /* hero stats are optional */
      }
    })();
  }, []);

  useEffect(() => {
    if (!email) {
      setRadars([]);
      return;
    }
    void (async () => {
      try {
        setRadars(await api.radars());
      } catch {
        setRadars([]);
      }
    })();
  }, [email]);

  useEffect(() => {
    void (async () => {
      try {
        setCountries(await api.countries(undefined, true));
      } catch {
        setCountries([]);
      }
    })();
  }, []);

  const onLiveSignal = useCallback(
    (signal: Signal) => {
      setSignals((prev) => {
        if (prev.some((s) => s.id === signal.id)) return prev;
        if (tab !== "all") return prev;
        return [signal, ...prev].slice(0, 30);
      });
      setTotal((prev) => prev + 1);
    },
    [tab],
  );

  const liveState = useLiveFeed(onLiveSignal);
  const hasFilters = Boolean(
    radarFilter || countryFilter || sourceFilter || minStrength > 0,
  );

  const sourceOptions = useMemo(() => {
    const seen = new Set<string>();
    signals.forEach((s) => seen.add(s.source_id));
    return [...seen];
  }, [signals]);

  return (
    <>
      {stats && !email && (
        <section className="hero">
          <div className="hero-kicker">
            <span className="live-dot" style={{ background: "var(--brand)" }} />
            Condition-driven monitoring
          </div>

          <h1 className="hero-title">
            Catch what&apos;s starting to trend{" "}
            <em>before it becomes obvious.</em>
          </h1>

          <p className="hero-sub">
            Signal Radar watches TikTok, YouTube, X, Reddit, Google Trends and
            more &mdash; and surfaces only what just started growing fast. You
            set the conditions once; it runs 24/7.
          </p>

          <div className="hero-actions">
            <a className="btn btn-lg btn-primary" href="#feed">
              Explore signals
            </a>
            <Link className="btn btn-lg btn-outline" href="/radars/new">
              Create your radar
            </Link>
          </div>

          <div className="hero-stats">
            <div>
              <div className="hero-stat-value">{stats.total_signals}</div>
              <div className="hero-stat-label">Signals tracked</div>
            </div>
            <div>
              <div className="hero-stat-value">{stats.breakout}</div>
              <div className="hero-stat-label">Breakouts</div>
            </div>
            <div>
              <div className="hero-stat-value">{stats.sources}</div>
              <div className="hero-stat-label">Sources live</div>
            </div>
            <div>
              <div className="hero-stat-value">{stats.countries}</div>
              <div className="hero-stat-label">Countries</div>
            </div>
          </div>
        </section>
      )}

      {stats && !email && (
        <section style={{ marginBottom: "var(--s6)" }}>
          <div className="section-title">How it works</div>
          <div className="steps">
            {STEPS.map((step, index) => (
              <div className="step" key={step.title}>
                <div className="step-index">{index + 1}</div>
                <div className="step-title">{step.title}</div>
                <div className="step-text">{step.text}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div id="feed">
        <div className="section-title">
          Live signals
          <span className="live" data-state={liveState}>
            <span className="live-dot" />
            {liveState === "live" ? "LIVE" : liveState.toUpperCase()}
          </span>
          <div className="spacer" />
          <span className="dim text-xs">{total} found</span>
        </div>

        <div className="tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              className="tab"
              data-active={tab === item.id}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="filters">
          {email && radars.length > 0 && (
            <FilterSelect
              label="Radar"
              value={radarFilter}
              onChange={setRadarFilter}
              options={radars.map((r) => ({ value: r.id, label: r.name }))}
              allLabel="All radars"
            />
          )}

          <FilterSelect
            label="Country"
            value={countryFilter}
            onChange={setCountryFilter}
            options={countries.map((c) => ({
              value: c.code,
              label: `${c.flag} ${countryName(c.code)}`,
            }))}
            allLabel="All countries"
          />

          {sourceOptions.length > 0 && (
            <FilterSelect
              label="Source"
              value={sourceFilter}
              onChange={setSourceFilter}
              options={sourceOptions.map((s) => ({
                value: s,
                label: sourceName(s),
              }))}
              allLabel="All sources"
            />
          )}

          <button
            className="filter"
            data-active={minStrength >= 50}
            onClick={() => setMinStrength(minStrength >= 50 ? 0 : 50)}
          >
            <span className="filter-label">Strength</span>
            {minStrength >= 50 ? "≥ 50" : "Any"}
          </button>

          {hasFilters && (
            <button
              className="filter"
              onClick={() => {
                setRadarFilter(null);
                setCountryFilter(null);
                setSourceFilter(null);
                setMinStrength(0);
              }}
            >
              Clear
            </button>
          )}
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
            <div className="empty-title">No signals match yet</div>
            <p className="empty-text">
              The worker collects every 15 minutes. Broaden the filters, or
              create a radar and it will start matching for you.
            </p>
            <Link className="btn btn-primary" href="/radars/new">
              Create a radar
            </Link>
          </div>
        )}

        {signals.map((signal) => (
          <SignalCard
            key={signal.id}
            signal={signal}
            signedIn={Boolean(email)}
          />
        ))}
      </div>
    </>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  label: string;
  value: string | null;
  onChange: (next: string | null) => void;
  options: { value: string; label: string }[];
  allLabel: string;
}) {
  return (
    <select
      className="filter"
      data-active={Boolean(value)}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">{`${label}: ${allLabel}`}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
