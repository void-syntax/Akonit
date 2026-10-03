"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const NAV = [
  { href: "/", label: "Signals", icon: "📡" },
  { href: "/radars", label: "Radars", icon: "🎯" },
  { href: "/saved", label: "Saved", icon: "🔖" },
  { href: "/profile", label: "Profile", icon: "👤" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/signals");
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";

  return (
    <div className="app">
      <header className="topbar">
        <div className="container topbar-inner">
          <Link href="/" className="brand">
            SIGNAL RADAR
            <span>early signals, 24/7</span>
          </Link>
          <div className="spacer" />
          <Link href="/settings" className="live" data-state="idle" title="Source health">
            <span className="live-dot" />
            LIVE
          </Link>
        </div>
      </header>

      <main className="page">
        <div className="container">{children}</div>
      </main>

      <nav className="tabbar">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            data-active={isActive(pathname, item.href)}
          >
            <span className="tab-icon">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}