"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FilterSelect } from "@/components/FilterSelect";
import { IntroHero } from "@/components/IntroHero";
import { TerminalLogStream } from "@/components/TerminalLogStream";
import { AnalyticsMiniBanner } from "@/components/AnalyticsMiniBanner";
import { SignalCard, SignalCardSkeleton } from "@/components/SignalCard";
import { SkeletonList } from "@/components/SkeletonList";
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
  const [loadingMore, setLoadingMore] = useState(false);
  const nextOffset = useRef(0);
  const [error, setError] = useState<string | null>(null);

  const [stats, setStats] = useState<PublicStats | null>(null);
  const [radars, setRadars] = useState<Radar[]>([]);
  const [radarFilter, setRadarFilter] = useState<string | null>(null);
  const [countryFilter, setCountryFilter] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [minStrength, setMinStrength] = useState(0);
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const query = useMemo(() => {
    const q: FeedQuery = { tab, limit: 100 };
    if (radarFilter) q.radar_id = radarFilter;
    if (countryFilter.length) q.country = countryFilter;
    if (sourceFilter.length) q.source = sourceFilter;
    if (tagFilter.length) q.tag = tagFilter;
    if (debouncedSearch.trim()) q.keyword = debouncedSearch.trim();
    if (minStrength > 0) q.min_strength = minStrength;
    return q;
  }, [tab, radarFilter, countryFilter, sourceFilter, tagFilter, debouncedSearch, minStrength]);
  const queryKey = JSON.stringify(query);
  const queryKeyRef = useRef(queryKey);
  queryKeyRef.current = queryKey;

  const liveState = useLiveFeed(
    query,
    useCallback((page) => {
      setSignals((prev) => {
        const existingIds = new Set(prev.map((s) => s.id));
        const trulyNew = page.items.filter((s) => !existingIds.has(s.id));
        if (trulyNew.length === 0) return prev;
        return [...trulyNew, ...prev];
      });
      setTotal(page.total);
    }, []),
  );

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const page = await api.signals({ ...query, offset: 0 }, signal ? { signal } : undefined);
      if (signal?.aborted) return;
      nextOffset.current = page.offset + page.items.length;
      setSignals(page.items);
      setTotal(page.total);
    } catch (err) {
      if (signal?.aborted) return;
      nextOffset.current = 0;
      setSignals([]);
      setError(err instanceof Error ? err.message : "Could not load signals");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    let active = true;
    const refreshStats = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const next = await api.stats();
        if (active) setStats(next);
      } catch {
        // Keep the latest good counts during brief API/network interruptions.
      }
    };
    void refreshStats();
    const timer = setInterval(() => void refreshStats(), 30_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void refreshStats();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
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



  const hasFilters = Boolean(
    radarFilter ||
      countryFilter.length ||
      sourceFilter.length ||
      tagFilter.length ||
      search.trim() ||
      minStrength > 0,
  );

  return (
    <>
      <IntroHero stats={stats} firstRun={radars.length === 0} />

      <div id="feed">
        <TerminalLogStream />
        <AnalyticsMiniBanner />

        <div className="section-title">
          Live signals
          <span className="live" data-state={liveState}>
            <span className="live-dot" />
            {liveState === "live" ? "LIVE" : liveState.toUpperCase()}
          </span>
          <div className="spacer" />
          <span className="dim text-xs">
            {signals.length.toLocaleString()} / {total.toLocaleString()} loaded
          </span>
        </div>

        <div className="tabs" role="tablist" aria-label="Filter signals by trend status">
          {TABS.map((item) => (
            <button
              key={item.id}
              className="tab"
              data-active={tab === item.id}
              role="tab"
              aria-selected={tab === item.id}
              aria-controls="signal-results"
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
            aria-pressed={minStrength >= 50}
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

        {error && (
          <div className="error-card" role="alert" aria-live="assertive">
            <div className="error-card-icon" aria-hidden="true">⚠</div>
            <div className="error-card-body">
              <div className="error-card-title">Could not load signals</div>
              <p className="error-card-msg">{error}</p>
            </div>
            <button
              className="btn btn-sm btn-primary error-card-retry"
              onClick={() => void load()}
            >
              Retry
            </button>
          </div>
        )}

        {loading && signals.length === 0 && <SkeletonList count={3} />}

        {!loading && !error && signals.length === 0 && (
          <div className="empty" role="status" aria-live="polite">
            <div className="empty-title">
              {search.trim()
                ? `No results for "${search.trim()}"`
                : hasFilters
                  ? "No signals match these filters"
                  : "No signals yet"}
            </div>
            <p className="empty-text">
              {search.trim()
                ? "Try a different keyword, or clear the search to browse all signals."
                : hasFilters
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

        <div id="signal-results" role="tabpanel" aria-label={`${tab} signals`}>
          {signals.map((signal) => (
            <SignalCard
              key={signal.id}
              signal={signal}
              onChange={(updated) =>
                setSignals((prev) =>
                  prev.map((item) => (item.id === updated.id ? updated : item)),
                )
              }
              onDelete={(id) =>
                setSignals((prev) => prev.filter((item) => item.id !== id))
              }
            />
          ))}
        </div>
        {!loading && !error && nextOffset.current < total && (
          <div className="feed-load-more">
            <button
              className="btn"
              disabled={loadingMore}
              onClick={async () => {
                const requestedQueryKey = queryKey;
                const offset = nextOffset.current;
                setLoadingMore(true);
                setError(null);
                try {
                  const nextQuery = { ...query, limit: 100, offset };
                  const page = await api.signals(nextQuery);
                  if (requestedQueryKey !== queryKeyRef.current) return;
                  nextOffset.current = offset + page.items.length;
                  setSignals((previous) => {
                    const seen = new Set(previous.map((signal) => signal.id));
                    return [...previous, ...page.items.filter((signal) => !seen.has(signal.id))];
                  });
                  setTotal(page.items.length === 0 ? Math.min(page.total, offset) : page.total);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Could not load more signals");
                } finally {
                  setLoadingMore(false);
                }
              }}
            >
              {loadingMore ? "Loading…" : `Load more (${(total - signals.length).toLocaleString()} left)`}
            </button>
          </div>
        )}
      </div>
    </>
  );
}


