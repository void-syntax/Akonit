"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/store/auth";

/**
 * There is no login in local mode.
 *
 * The API resolves a single local account automatically, so this route only
 * exists to explain that instead of leaving a dead "Sign in" button behind. It
 * confirms the account resolved and then redirects to the feed.
 */
export default function LoginPage() {
  const router = useRouter();
  const { email, hydrate } = useAuth();

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (email) router.replace("/");
  }, [email, router]);

  return (
    <div className="page-narrow">
      <div className="section-title">SIGNAL RADAR</div>

      <div className="panel panel-pad">
        <h1 className="panel-title">No account needed</h1>
        <p className="muted">
          Signal Radar runs on your own machine, so there is nothing to log into.
          Your radars, saved signals and settings live in your local database.
        </p>

        {email ? (
          <p className="muted mono text-xs">
            Local account ready: {email}
          </p>
        ) : (
          <p className="muted">
            Connecting to the local API at{" "}
            <code className="mono">{api.baseUrl()}</code>…
          </p>
        )}

        <div className="row gap">
          <Link className="btn btn-primary" href="/">
            Go to signals
          </Link>
          <Link className="btn btn-ghost" href="/radars/new">
            Create a radar
          </Link>
        </div>
      </div>
    </div>
  );
}