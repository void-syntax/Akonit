"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { sourceName } from "@/lib/format";
import type { Country, Radar, SourceInfo, Tag } from "@/lib/types";

export default function RadarsPage() {
  const [radars, setRadars] = useState<Radar[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const [r, c, s, t] = await Promise.all([
          api.radars(),
          api.countries(),
          api.sources(),
          api.tags(),
        ]);
        setRadars(r);
        setCountries(c);
        setSources(s);
        setTags(t);
      } catch {
        /* handled by empty state */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <>
      <div className="section-title">MY RADARS</div>

      {loading && <p className="muted">Loading radars…</p>}

      {!loading && radars.length === 0 && (
        <div className="empty">
          <div className="empty-title">No radars yet</div>
          <p className="muted">
            Each radar is a 24/7 watcher. Create one for anything you care about.
          </p>
        </div>
      )}

      <div className="radar-grid">
        {radars.map((radar) => (
          <div key={radar.id} className="radar-card">
            <div className="radar-name">
              <span>{radar.emoji ?? "🎯"}</span>
              <span>{radar.name}</span>
            </div>

            <div className="radar-meta">
              {radar.countries.length > 0
                ? radar.countries
                    .map(
                      (code) =>
                        countries.find((c) => c.code === code)?.flag ?? code,
                    )
                    .join(" ")
                : "All countries"}
              {" · "}
              {radar.source_ids.length > 0
                ? radar.source_ids.map(sourceName).join(", ")
                : "All sources"}
              {radar.tag_slugs.length > 0 && (
                <>
                  {" · "}
                  {radar.tag_slugs.slice(0, 3).join(", ")}
                </>
              )}
            </div>

            <div className="row">
              <span className="radar-count">{radar.active_signal_count}</span>
              <span className="muted" style={{ fontSize: "0.8rem" }}>
                active signals
              </span>
            </div>

            <div className="row" style={{ marginTop: 14 }}>
              <Link
                className="btn btn-sm"
                href={`/radars/${radar.id}`}
              >
                Open feed
              </Link>
              <a
                className="btn btn-sm"
                href={`/?radar=${radar.id}`}
              >
                View signals
              </a>
              <div className="spacer" />
              <span className="dim" style={{ fontSize: "0.72rem" }}>
                {radar.notification_frequency.replace("_", " ").toLowerCase()}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 18 }}>
        <Link className="btn btn-primary" href="/radars/new">
          + Create Radar
        </Link>
      </div>
    </>
  );
}