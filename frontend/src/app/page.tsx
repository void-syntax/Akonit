"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { FilterSelect } from "@/components/FilterSelect";
import { IntroHero } from "@/components/IntroHero";
import { SignalCard, SignalCardSkeleton } from "@/components/SignalCard";
import { api, type FeedQuery } from "@/lib/api";
import { countryName, sourceName } from "@/lib/format";
import type {
  Country,
  PublicStats,
  Radar,
  Signal,
  SourceInfo,
  Tag,
} from "@/lib/types";
import { useLiveFeed } from "@/lib/useLiveFeed";
import { useAuth } from "@/store/auth";

const TABS = [
  { id: "all", label: "ALL" },
  { id: "rising", label: "RISING" },
  { id: "breakout", label: "BREAKOUT" },
  { id: "new", label: "NEW" },
] as const;

type TabId = (typeof TABS)[number]["id"];

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
  const [countryFilter, setCountryFilter] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [minStrength, setMinStrength] = useState(0);
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query: FeedQuery = { tab, limit: 30 };
      if (radarFilter) query.radar_id = radarFilter;
      if (countryFilter.length) query.country = countryFilter;
      if (sourceFilter.length) query.source = sourceFilter;
      if (tagFilter.length) query.tag = tagFilter;
      if (search.trim()) query.keyword = search.trim();
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
  }, [
    tab,
    radarFilter,
    countryFilter,
    sourceFilter,
    tagFilter,
    search,
    minStrength,
  ]);

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

  // Sources and tags drive the filter bar, so they load once and stay put:
  // re-fetching them on every tab change would make the UI feel unstable.
  useEffect(() => {
    void (async () => {
      try {
        setSources(await api.sources());
      } catch {
        setSources([]);
      }
      try {
        setTags(await api.tags());
      } catch {
        setTags([]);
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
    radarFilter ||
      countryFilter.length ||
      sourceFilter.length ||
      tagFilter.length ||
      search.trim() ||
      minStrength > 0,
  );

  const sourceOptions = useMemo(() => {
    const seen = new Set<string>();
    signals.forEach((s) => seen.add(s.source_id));
    return [...seen];
  }, [signals]);

  return (
    <>
      <IntroHero stats={stats} firstRun={radars.length === 0} />

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
          <input
            className="filter filter-search"
            type="search"
            value={search}
            placeholder="Search titles and descriptions…"
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search signals"
          />

          {radars.length > 0 && (
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

          <FilterSelect
            label="Source"
            value={sourceFilter}
            onChange={setSourceFilter}
            options={sources.map((s) => ({
              value: s.id,
              label: sourceName(s.id),
            }))}
            allLabel="All sources"
          />

          <FilterSelect
            label="Tag"
            value={tagFilter}
            onChange={setTagFilter}
            options={tags.map((t) => ({
              value: t.slug,
              label: `${t.emoji ?? ""} ${t.name}`.trim(),
            }))}
            allLabel="All tags"
          />

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
                setCountryFilter([]);
                setSourceFilter([]);
                setTagFilter([]);
                setSearch("");
                setMinStrength(0);
              }}
            >
              Clear
            </button>
          )}
        </div>

        {/* The active tag selection is the answer to "what am I looking at?" */}
        {tagFilter.length > 0 && (
          <div className="card-tags filter-active">
            <span className="dim text-xs">Filtered by</span>
            {tagFilter.map((slug) => (
              <button
                key={slug}
                className="tag-chip tag-chip-active"
                onClick={() =>
                  setTagFilter((prev) => prev.filter((t) => t !== slug))
                }
              >
                #{slug.replace(/-/g, " ")} ×
              </button>
            ))}
          </div>
        )}

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
            <div className="empty-title">
              {hasFilters ? "No signals match these filters" : "No signals yet"}
            </div>
            <p className="empty-text">
              {hasFilters
                ? "Try removing a filter, or widen the country and tag selection."
                : "The collector runs every minute. It needs a moment to fetch the first cycle."}
            </p>
            {hasFilters ? (
              <button
                className="btn btn-primary"
                onClick={() => {
                  setRadarFilter(null);
                  setCountryFilter([]);
                  setSourceFilter([]);
                  setTagFilter([]);
                  setSearch("");
                  setMinStrength(0);
                }}
              >
                Clear filters
              </button>
            ) : (
              <Link className="btn btn-primary" href="/radars/new">
                Create a radar
              </Link>
            )}
          </div>
        )}

        {signals.map((signal) => (
          <SignalCard
            key={signal.id}
            signal={signal}
            onChange={(updated) =>
              setSignals((prev) =>
                prev.map((item) => (item.id === updated.id ? updated : item)),
              )
            }
          />
        ))}
      </div>
    </>
  );
}


