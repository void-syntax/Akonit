"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import {
  BookmarkIcon,
  CompassIcon,
  FireIcon,
  PlusIcon,
  RadarIcon,
  RadarIcon as LogoIcon,
  SearchIcon,
  UserIcon,
} from "@/components/icons";
import { api } from "@/lib/api";
import { useAuth } from "@/store/auth";
import type { LiveState } from "@/lib/useLiveFeed";

const NAV = [
  { href: "/", label: "Signals", Icon: CompassIcon },
  { href: "/radars", label: "Radars", Icon: RadarIcon },
  { href: "/discover", label: "Discover", Icon: SearchIcon },
  { href: "/saved", label: "Saved", Icon: BookmarkIcon },
  { href: "/profile", label: "Profile", Icon: UserIcon },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/radars") {
    return pathname === "/radars" || pathname.startsWith("/radars/");
  }
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { email, hydrate } = useAuth();
  const [live, setLive] = useState<LiveState>("connecting");
  const [breakout, setBreakout] = useState(0);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  // Lightweight probe so the header badge reflects reality, not a guess.
  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        await api.sourceHealth();
        if (!active) return;
        // Reaching the API is what "online" means. An empty summary means no
        // source has reported yet, which is a cold start, not an outage, so it
        // must not be shown as one.
        setLive("live");
      } catch {
        if (active) setLive("offline");
      }
      try {
        const stats = await api.stats();
        if (active) setBreakout(stats.breakout);
      } catch {
        /* counts are cosmetic here */
      }
    }

    void poll();
    const timer = setInterval(poll, 30_000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="container topbar-inner">
          <Link href="/" className="brand">
            <span className="brand-mark">
              <LogoIcon size={17} />
            </span>
            <span className="brand-text">
              SIGNAL RADAR
              <span className="brand-sub">early signals, 24/7</span>
            </span>
          </Link>

          {/* Desktop navigation. The bottom tabbar is hidden above 768px, so
              without this there is no way to move between sections at all. */}
          <nav className="mainnav" aria-label="Main">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="mainnav-item"
                data-active={isActive(pathname, item.href)}
              >
                <item.Icon size={16} />
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="spacer" />

          <span className="live" data-state={live}>
            <span className="live-dot" />
            {live === "live" ? "LIVE" : live.toUpperCase()}
          </span>

          {breakout > 0 && (
            <Link href="/?tab=breakout" className="topbar-count" title="Signals breaking out right now">
              <FireIcon size={13} />
              {breakout}
            </Link>
          )}

          <Link href="/radars/new" className="btn btn-sm btn-primary topbar-cta">
            <PlusIcon size={14} />
            <span className="desktop-only">Radar</span>
          </Link>

          {email ? (
            <Link href="/profile" className="btn btn-sm btn-ghost" title="Tags and settings">
              <UserIcon size={15} />
            </Link>
          ) : (
            <span className="badge badge-neutral" title="Waiting for the local API">
              Offline
            </span>
          )}
        </div>
      </header>

      <main className="page">
        <div className="container">{children}</div>
      </main>

      <nav className="tabbar" aria-label="Sections">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="tabbar-item"
            data-active={isActive(pathname, item.href)}
          >
            <item.Icon size={21} />
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}