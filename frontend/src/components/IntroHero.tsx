"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  BoltIcon,
  CompassIcon,
  FireIcon,
  RadarIcon,
  SparkIcon,
  TrendingUpIcon,
  CloseIcon,
} from "@/components/icons";
import type { PublicStats } from "@/lib/types";

const DISMISS_KEY = "signal-radar:intro-dismissed";

const STEPS = [
  {
    title: "You set the conditions",
    text: "Countries, sources, tags, growth and strength thresholds. No code, no SQL.",
  },
  {
    title: "The collector runs every minute",
    text: "Free public sources, measured twice so growth is real rather than guessed.",
  },
  {
    title: "Signals surface early",
    text: "Only what just started accelerating, ranked by how strong the move is.",
  },
  {
    title: "You get notified",
    text: "Browser push or Telegram the moment a radar matches.",
  },
];

const STATUSES = [
  {
    label: "NEW",
    icon: SparkIcon,
    tone: "new",
    text: "first seen, not enough history to measure growth yet",
  },
  {
    label: "RISING",
    icon: TrendingUpIcon,
    tone: "rising",
    text: "measured activity is climbing between collections",
  },
  {
    label: "BREAKOUT",
    icon: FireIcon,
    tone: "breakout",
    text: "sharp acceleration, the ones worth acting on now",
  },
] as const;

interface Props {
  stats: PublicStats | null;
  /** True until the user has built their first radar. */
  firstRun: boolean;
}

/**
 * The explanation the product owes the user on arrival.
 *
 * It answers what this is, what a signal means, what is live right now, and how
 * to start — before any data is on screen. Shown on the first run and
 * dismissible, because a permanent marketing block would push the actual feed
 * below the fold.
 */
export function IntroHero({ stats, firstRun }: Props) {
  const [dismissed, setDismissed] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      setDismissed(window.localStorage.getItem(DISMISS_KEY) === "1");
    } catch {
      /* private mode: just show it */
    }
  }, []);

  function dismiss() {
    setDismissed(true);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* nothing to persist to */
    }
  }

  // Before hydration the stored flag is unknown, so render nothing rather than
  // flashing the hero at someone who already dismissed it.
  if (!mounted || dismissed) return null;

  return (
    <section className="hero">
      <button
        className="hero-dismiss"
        onClick={dismiss}
        aria-label="Hide this introduction"
        title="Hide"
      >
        <CloseIcon size={15} />
      </button>

      <div className="hero-kicker">
        <span className="live-dot" style={{ background: "var(--brand)" }} />
        Runs on your machine · collects every 60s
      </div>

      <h1 className="hero-title">
        Catch what&apos;s starting to trend{" "}
        <em>before it becomes obvious.</em>
      </h1>

      <p className="hero-sub">
        Signal Radar measures TikTok, YouTube, X, Reddit, Google Trends and more
        every minute, and shows only what just started growing fast. Tell it what
        to watch with a <strong>radar</strong> — it does the rest.
      </p>

      <div className="hero-actions">
        <a className="btn btn-lg btn-primary" href="#feed">
          <CompassIcon size={17} />
          Explore signals
        </a>
        <Link className="btn btn-lg btn-outline" href="/radars/new">
          <RadarIcon size={17} />
          Create your radar
        </Link>
      </div>

      {firstRun && (
        <p className="hero-note">
          <BoltIcon size={13} />
          No radar yet — everything below is global. Build one to narrow it to
          the topics you care about.
        </p>
      )}

      {stats && (
        <div className="hero-stats">
          <div>
            <div className="hero-stat-value">{stats.total_signals}</div>
            <div className="hero-stat-label">Signals tracked</div>
          </div>
          <div>
            <div className="hero-stat-value">{stats.breakout}</div>
            <div className="hero-stat-label">Breaking out</div>
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
      )}

      {/* What the status badges on every card actually mean. Without this the
          feed is just coloured pills with no explanation. */}
      <div className="hero-legend">
        {STATUSES.map((status) => (
          <div className="legend-row" key={status.label}>
            <span className={`badge badge-${status.tone}`}>
              <status.icon size={12} />
              {status.label}
            </span>
            <span className="legend-text">{status.text}</span>
          </div>
        ))}
      </div>

      <div className="hero-how">
        {STEPS.map((step, index) => (
          <div className="step" key={step.title}>
            <div className="step-index">{index + 1}</div>
            <div className="step-title">{step.title}</div>
            <div className="step-text">{step.text}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
