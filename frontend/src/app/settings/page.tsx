"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CheckIcon } from "@/components/icons";
import { api } from "@/lib/api";
import { countryName } from "@/lib/format";
import type {
  Country,
  NotificationFrequency,
  NotificationStatus,
  Profile,
  SourceInfo,
} from "@/lib/types";
import { useAuth } from "@/store/auth";

const FREQUENCIES: { value: NotificationFrequency; label: string }[] = [
  { value: "OFF", label: "Off — never notify" },
  { value: "INSTANT", label: "Instant — as soon as it matches" },
  { value: "EVERY_15_MIN", label: "Every 15 minutes" },
  { value: "HOURLY", label: "Hourly digest" },
  { value: "DAILY_DIGEST", label: "Daily digest" },
];

function toggleInList(list: string[], value: string): string[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

/**
 * The server sends the VAPID key as unpadded url-safe base64, but the Push API
 * wants raw bytes.
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const normalised = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const raw = window.atob(normalised);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}

export default function SettingsPage() {
  const { email, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [status, setStatus] = useState<NotificationStatus | null>(null);
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatId, setChatId] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramMessage, setTelegramMessage] = useState<string | null>(null);
  const [pushState, setPushState] = useState<"idle" | "on" | "unsupported">(
    "idle",
  );

  useEffect(() => {
    if (!email) return;
    void (async () => {
      try {
        const [p, s, c, src] = await Promise.all([
          api.profile(),
          api.notificationStatus(),
          api.countries(undefined, true),
          api.sources(),
        ]);
        setProfile(p);
        setStatus(s);
        setChatId(p.telegram_chat_id ?? "");
        setCountries(c);
        setSources(src.filter((item) => item.status !== "OFFLINE"));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load settings");
      }
    })();
  }, [email]);

  async function patch(payload: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      setProfile(await api.updateProfile(payload));
      setSaved(true);
      setTimeout(() => setSaved(false), 2200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function enablePush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setPushState("unsupported");
      return;
    }
    try {
      // A VAPID key is mandatory: browsers reject a subscription without one.
      const { public_key: vapidKey } = await api.pushPublicKey();
      if (!vapidKey) {
        setError(
          "Push is not configured on the server. Set VAPID_PUBLIC_KEY and " +
            "VAPID_PRIVATE_KEY in backend/.env (generate them with " +
            "`python -m tools.gen_vapid`).",
        );
        return;
      }

      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setError("Browser blocked notifications for this site.");
        return;
      }

      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });

      const json = subscription.toJSON() as {
        endpoint?: string;
        keys?: Record<string, string>;
      };
      if (!json.endpoint) {
        throw new Error("browser returned a subscription without an endpoint");
      }

      await api.subscribePush({
        endpoint: json.endpoint,
        keys: json.keys ?? {},
      });
      setPushState("on");
    } catch (err) {
      setError(
        err instanceof Error
          ? `Push failed: ${err.message}`
          : "Push notifications unavailable",
      );
    }
  }

  async function linkTelegram() {
    await patch({ telegram_chat_id: chatId });
    try {
      setStatus(await api.notificationStatus());
    } catch {
      /* status refresh is optional */
    }
  }

  async function configureTelegram() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.configureTelegramBot(telegramToken);
      setTelegramToken("");
      setStatus(await api.notificationStatus());
      setTelegramMessage(result.bot_username ? `Connected to @${result.bot_username}. Save the chat ID and send a test.` : "Bot connected. Save the chat ID and send a test.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect Telegram bot");
    } finally {
      setBusy(false);
    }
  }

  async function testTelegram() {
    setBusy(true);
    setError(null);
    try {
      await api.testTelegram();
      setTelegramMessage("Test message sent. Open Telegram to confirm it arrived.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Telegram test failed");
    } finally {
      setBusy(false);
    }
  }

  async function findTelegramChat() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.findTelegramChat();
      setChatId(result.chat_id);
      setTelegramMessage(`Found Telegram chat${result.name ? ` for ${result.name}` : ""}. Save it, then send a test.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not find Telegram chat");
    } finally {
      setBusy(false);
    }
  }

  async function toggleTelegram() {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      await api.toggleTelegram(!profile.telegram_alerts_enabled);
      setProfile(await api.profile());
      setStatus(await api.notificationStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update Telegram alerts");
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) return <p className="muted">Loading…</p>;

  if (!email) {
    return (
      <div className="empty" role="status" aria-live="polite">
        <div className="empty-title">Cannot reach the local API</div>
        <p className="empty-text">
          Notification channels, quiet hours and defaults are stored in your
          local database. Start the collector with{" "}
          <code className="mono">docker compose up</code> and reload.
        </p>
        <button className="btn btn-primary" onClick={() => location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  if (!profile) {
    return (
      <>
        {error && <div className="alert alert-error" role="alert" aria-live="assertive">{error}</div>}
        <p className="muted">Loading settings…</p>
      </>
    );
  }

  const quiet = profile.quiet_hours ?? {
    start: "23:00",
    end: "07:00",
    enabled: false,
  };

  return (
    <>
      <div className="section-title">
        Notifications
        {saved && (
          <span className="badge badge-accent">
            <CheckIcon size={12} /> Saved
          </span>
        )}
      </div>

      <div className="panel">
        <div className="field">
          <label className="field-label" htmlFor="sfreq">
            Default frequency for new radars
          </label>
          <select
            id="sfreq"
            value={profile.default_frequency}
            disabled={busy}
            onChange={(e) => patch({ default_frequency: e.target.value })}
          >
            {FREQUENCIES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <span className="field-label">Signal strength threshold</span>
          <div className="slider-row">
            <input
              type="range"
              min={0}
              max={100}
              value={profile.signal_threshold}
              disabled={busy}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  signal_threshold: Number(e.target.value),
                })
              }
              onMouseUp={(e) =>
                patch({ signal_threshold: Number(e.currentTarget.value) })
              }
              onTouchEnd={(e) =>
                patch({ signal_threshold: Number(e.currentTarget.value) })
              }
            />
            <span className="slider-value">{profile.signal_threshold}</span>
          </div>
          <div className="field-hint">
            Signals weaker than this are ignored when a radar has no explicit
            threshold.
          </div>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="qstart">
            Quiet hours
          </label>
          <div className="row">
            <button
              className="chip"
              data-active={quiet.enabled}
              disabled={busy}
              onClick={() =>
                patch({ quiet_hours: { ...quiet, enabled: !quiet.enabled } })
              }
              type="button"
            >
              {quiet.enabled ? "ON" : "OFF"}
            </button>
            <input
              id="qstart"
              type="time"
              value={String(quiet.start || "")}
              disabled={busy || !quiet.enabled}
              style={{ maxWidth: 130 }}
              onChange={(e) =>
                patch({ quiet_hours: { ...quiet, start: e.target.value } })
              }
            />
            <span className="dim">to</span>
            <input
              type="time"
              value={String(quiet.end || "")}
              disabled={busy || !quiet.enabled}
              style={{ maxWidth: 130 }}
              onChange={(e) =>
                patch({ quiet_hours: { ...quiet, end: e.target.value } })
              }
            />
          </div>
          <div className="field-hint">
            No notifications are delivered inside this window.
          </div>
        </div>
      </div>

      <div className="section-title">Channels</div>

      <div className="panel">
        <div className="row">
          <div>
            <div className="step-title">Browser push</div>
            <div className="field-hint">
              {pushState === "unsupported"
                ? "This browser does not support web push."
                : status?.push_configured
                  ? "VAPID keys are configured on the server."
                  : "Requires VAPID keys in .env (see .env.example)."}
            </div>
          </div>
          <div className="spacer" />
          <button
            className="btn"
            data-active={pushState === "on"}
            onClick={enablePush}
            disabled={pushState === "unsupported"}
            type="button"
          >
            {pushState === "on" ? "Enabled" : "Enable push"}
          </button>
        </div>

        <div className="field" style={{ marginTop: "var(--s4)" }}>
          <div className="step-title">Telegram alerts</div>
          <div className="field-hint">Create a bot with @BotFather, open it and press Start. Your token is encrypted locally and never shown again.</div>
          {telegramMessage && <div className="field-hint" role="status">{telegramMessage}</div>}
          <div className="row" style={{ marginTop: 8 }}>
            <input aria-label="Telegram bot token" type="password" autoComplete="new-password" placeholder={status?.bot_configured ? "Bot connected — enter a new token to replace" : "Paste token from @BotFather"} value={telegramToken} onChange={(e) => setTelegramToken(e.target.value)} style={{ flex: 1 }} />
            <button className="btn btn-primary" onClick={configureTelegram} disabled={busy || !telegramToken.trim()} type="button">Verify and save bot</button>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <input aria-label="Telegram chat ID" inputMode="numeric" placeholder="Your numeric chat ID" value={chatId} onChange={(e) => setChatId(e.target.value)} style={{ maxWidth: 220 }} />
            <button className="btn" onClick={findTelegramChat} disabled={busy || !status?.bot_configured} type="button">Find my chat</button>
            <button className="btn" onClick={linkTelegram} disabled={busy || !chatId.trim()} type="button">Save chat ID</button>
            <button className="btn" onClick={testTelegram} disabled={busy || !status?.bot_configured || !status.linked} type="button">Send test</button>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="chip" data-active={profile.telegram_alerts_enabled} disabled={busy || !status?.bot_configured || !status.linked} onClick={toggleTelegram} type="button">Alerts {profile.telegram_alerts_enabled ? "ON" : "OFF"}</button>
            <span className="field-hint">Send /start to your bot first, then use Find my chat.</span>
          </div>
        </div>
      </div>

      <div className="section-title">Defaults for new radars</div>

      <div className="panel">
        <div className="field">
          <span className="field-label">Default countries</span>
          <div className="chip-picker">
            {countries.map((c) => (
              <button
                key={c.code}
                className="chip"
                data-active={profile.default_countries.includes(c.code)}
                disabled={busy}
                onClick={() =>
                  patch({
                    default_countries: toggleInList(
                      profile.default_countries,
                      c.code,
                    ),
                  })
                }
                type="button"
              >
                {c.flag} {countryName(c.code)}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <span className="field-label">Default sources</span>
          <div className="chip-picker">
            {sources.map((s) => (
              <button
                key={s.id}
                className="chip"
                data-active={profile.default_sources.includes(s.id)}
                disabled={busy}
                onClick={() =>
                  patch({
                    default_sources: toggleInList(
                      profile.default_sources,
                      s.id,
                    ),
                  })
                }
                type="button"
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="section-title">Appearance</div>

      <div className="panel">
        <span className="field-label">Theme</span>
        <div className="row" style={{ marginTop: 8 }}>
          {["dark", "system"].map((option) => (
            <button
              key={option}
              className="chip"
              data-active={profile.theme === option}
              disabled={busy}
              onClick={() => patch({ theme: option })}
              type="button"
            >
              {option === "dark" ? "Dark (default)" : "Match system"}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="alert alert-error" role="alert" aria-live="assertive">{error}</div>}
    </>
  );
}
