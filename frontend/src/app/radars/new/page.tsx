"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConditionBuilder } from "@/components/ConditionBuilder";
import { api } from "@/lib/api";
import type {
  Condition,
  ConditionGroup,
  Country,
  NotificationFrequency,
  SourceInfo,
  Tag,
} from "@/lib/types";

const FREQUENCIES: { value: NotificationFrequency; label: string }[] = [
  { value: "OFF", label: "Off" },
  { value: "INSTANT", label: "Instant" },
  { value: "EVERY_15_MIN", label: "Every 15 minutes" },
  { value: "HOURLY", label: "Hourly" },
  { value: "DAILY_DIGEST", label: "Daily digest" },
];

interface Suggestion {
  emoji: string;
  name: string;
  countries: string[];
  sources: string[];
  tags: string[];
}

const SUGGESTIONS: Suggestion[] = [
  {
    emoji: "🇰🇷",
    name: "Korea Makeup",
    countries: ["KR"],
    sources: ["tiktok", "youtube"],
    tags: ["makeup", "skincare"],
  },
  {
    emoji: "🇺🇸",
    name: "USA Pranks",
    countries: ["US"],
    sources: ["tiktok", "x_trends", "reddit"],
    tags: ["pranks", "tiktok-pranks"],
  },
  {
    emoji: "🤖",
    name: "Free AI",
    countries: [],
    sources: ["github", "huggingface"],
    tags: ["free-ai", "ai-agents", "open-source-ai"],
  },
  {
    emoji: "💰",
    name: "Money",
    countries: [],
    sources: ["reddit", "tiktok"],
    tags: ["side-hustle", "making-money"],
  },
  {
    emoji: "🔥",
    name: "Viral Products",
    countries: [],
    sources: ["tiktok", "producthunt"],
    tags: ["viral-products", "new-products"],
  },
];

const EMPTY: ConditionGroup = {
  op: "AND",
  children: [],
  is_exclude: false,
};

export default function NewRadarPage() {
  const router = useRouter();
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [name, setName] = useState("");
  const [emoji, setEmoji] = useState("🎯");
  const [threshold, setThreshold] = useState(0);
  const [frequency, setFrequency] =
    useState<NotificationFrequency>("INSTANT");
  const [channels, setChannels] = useState<string[]>(["WEB_PUSH"]);
  const [conditions, setConditions] = useState<ConditionGroup>(EMPTY);
  const [preview, setPreview] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [c, s, t] = await Promise.all([
          api.countries(undefined, true),
          api.sources(),
          api.tags(),
        ]);
        setCountries(c);
        setSources(s);
        setTags(t);
      } catch {
        /* the builder still works without options */
      }
    })();
  }, []);

  function applySuggestion(s: Suggestion) {
    setName(s.name);
    setEmoji(s.emoji);
    const children: (ConditionGroup | Condition)[] = [];
    if (s.countries.length) {
      children.push({ type: "COUNTRY", operator: "IN", value: s.countries });
    }
    children.push({ type: "SOURCE", operator: "IN", value: s.sources });
    children.push({ type: "TAG", operator: "IN", value: s.tags });
    setConditions({ op: "AND", children, is_exclude: false });
  }

  async function runPreview() {
    setPreview(null);
    try {
      const result = await api.previewConditions(conditions);
      setPreview(result.matched);
    } catch {
      setPreview(-1);
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const radar = await api.createRadar({
        name,
        emoji,
        conditions,
        signal_threshold: threshold,
        notification_frequency: frequency,
        notification_channels: channels,
      });
      router.push(`/radars/${radar.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create radar");
    } finally {
      setBusy(false);
    }
  }

return (
    <>
      <div className="section-title">CREATE RADAR</div>

      <div className="builder" style={{ marginBottom: 12 }}>
        <span className="field-label">Start from a template</span>
        <div className="row" style={{ marginTop: 8 }}>
          {SUGGESTIONS.map((s) => (
            <button
              key={s.name}
              className="btn btn-sm"
              onClick={() => applySuggestion(s)}
            >
              {s.emoji} {s.name}
            </button>
          ))}
        </div>
      </div>

      <div className="builder">
        <div className="grid-2" style={{ marginBottom: 12 }}>
          <div>
            <label className="field-label" htmlFor="rname">
              Radar name
            </label>
            <input
              id="rname"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Korea Makeup"
            />
          </div>
          <div>
            <label className="field-label" htmlFor="remoji">
              Emoji
            </label>
            <input
              id="remoji"
              value={emoji}
              onChange={(e) => setEmoji(e.target.value)}
              maxLength={4}
            />
          </div>
        </div>

        <ConditionBuilder
          value={conditions}
          onChange={setConditions}
          countries={countries}
          sources={sources}
          tags={tags}
        />
      </div>

      <div className="builder" style={{ marginTop: 12 }}>
        <div className="section-title" style={{ margin: "0 0 10px" }}>
          NOTIFICATIONS
        </div>

        <div className="grid-2">
          <div>
            <label className="field-label" htmlFor="freq">
              Frequency
            </label>
            <select
              id="freq"
              value={frequency}
              onChange={(e) =>
                setFrequency(e.target.value as NotificationFrequency)
              }
            >
              {FREQUENCIES.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="thr">
              Signal strength threshold
            </label>
            <input
              id="thr"
              type="number"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value) || 0)}
            />
          </div>
        </div>

        <span className="field-label" style={{ marginTop: 12 }}>
          Channels
        </span>
        <div className="row" style={{ marginTop: 8 }}>
          {[
            { id: "WEB_PUSH", label: "🔔 Browser push" },
            { id: "TELEGRAM", label: "✈️ Telegram" },
          ].map((c) => (
            <button
              key={c.id}
              className="btn btn-sm"
              data-active={channels.includes(c.id)}
              onClick={() =>
                setChannels((prev) =>
                  prev.includes(c.id)
                    ? prev.filter((x) => x !== c.id)
                    : [...prev, c.id],
                )
              }
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="error" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}

      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn" onClick={runPreview}>
          Preview matches
        </button>
        {preview !== null && (
          <span className="muted">
            {preview < 0
              ? "preview failed"
              : `${preview} signals would match right now`}
          </span>
        )}
        <div className="spacer" />
        <button
          className="btn btn-primary"
          onClick={submit}
          disabled={busy || name.trim().length < 2}
        >
          {busy ? "Creating…" : "Create Radar"}
        </button>
      </div>
    </>
  );
}
