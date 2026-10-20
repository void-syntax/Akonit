"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConditionBuilder } from "@/components/ConditionBuilder";
import { api } from "@/lib/api";
import type {
  RadarCondition,
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

const TEMPLATES: {
  emoji: string;
  name: string;
  countries: string[];
  sources: string[];
  tags: string[];
}[] = [
  {
    emoji: "\u{1F1F0}\u{1F1F7}",
    name: "Korea Makeup",
    countries: ["KR"],
    sources: ["tiktok", "youtube"],
    tags: ["makeup", "skincare"],
  },
  {
    emoji: "\u{1F1FA}\u{1F1F8}",
    name: "USA Pranks",
    countries: ["US"],
    sources: ["tiktok", "x_trends", "reddit"],
    tags: ["pranks", "tiktok-pranks"],
  },
  {
    emoji: "\u{1F916}",
    name: "Free AI",
    countries: [],
    sources: ["github", "huggingface"],
    tags: ["free-ai", "ai-agents", "open-source-ai"],
  },
  {
    emoji: "\u{1F4B0}",
    name: "Money",
    countries: [],
    sources: ["reddit", "tiktok"],
    tags: ["side-hustle", "making-money"],
  },
  {
    emoji: "\u{1F525}",
    name: "Viral Products",
    countries: [],
    sources: ["tiktok", "producthunt"],
    tags: ["viral-products", "new-products"],
  },
];

const EMPTY: ConditionGroup = { op: "AND", children: [], is_exclude: false };

export default function NewRadarPage() {
  const router = useRouter();
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [name, setName] = useState("");
  const [emoji, setEmoji] = useState("\u{1F3AF}");
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
        setSources(s.filter((item) => item.status !== "OFFLINE"));
        setTags(t);
      } catch {
        /* the builder still works without option lists */
      }
    })();
  }, []);

  function applyTemplate(template: (typeof TEMPLATES)[number]) {
    setName(template.name);
    setEmoji(template.emoji);
    const children: (ConditionGroup | RadarCondition)[] = [];
    if (template.countries.length) {
      children.push({
        type: "COUNTRY",
        operator: "IN",
        value: template.countries,
      });
    }
    children.push({ type: "SOURCE", operator: "IN", value: template.sources });
    children.push({ type: "TAG", operator: "IN", value: template.tags });
    children.push({ type: "GROWTH", operator: "GT", value: 100 });
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
      <div className="row" style={{ marginBottom: "var(--s4)" }}>
        <Link className="btn btn-sm btn-ghost" href="/radars">
          ← Radars
        </Link>
      </div>

      <div className="section-title">Create radar</div>

      <div className="panel">
        <span className="field-label">Start from a template</span>
        <div className="row" style={{ marginTop: 8 }}>
          {TEMPLATES.map((template) => (
            <button
              key={template.name}
              className="chip"
              type="button"
              onClick={() => applyTemplate(template)}
            >
              {template.emoji} {template.name}
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="grid-2" style={{ marginBottom: "var(--s3)" }}>
          <div className="field">
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
          <div className="field">
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
          previewCount={preview}
        />
      </div>

      <div className="panel">
        <div className="section-title" style={{ marginTop: 0 }}>
          Notifications
        </div>

        <div className="grid-2">
          <div className="field">
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
              {FREQUENCIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="thr">
              Signal strength threshold
            </label>
            <div className="slider-row">
              <input
                id="thr"
                type="range"
                min={0}
                max={100}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
              <span className="slider-value">{threshold}</span>
            </div>
          </div>
        </div>

        <span className="field-label">Channels</span>
        <div className="row" style={{ marginTop: 8 }}>
          {[
            { id: "WEB_PUSH", label: "\u{1F514} Browser push" },
            { id: "TELEGRAM", label: "\u{2708} Telegram" },
          ].map((channel) => (
            <button
              key={channel.id}
              className="chip"
              type="button"
              data-active={channels.includes(channel.id)}
              onClick={() =>
                setChannels((prev) =>
                  prev.includes(channel.id)
                    ? prev.filter((x) => x !== channel.id)
                    : [...prev, channel.id],
                )
              }
            >
              {channel.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="alert alert-error" role="alert" aria-live="assertive">{error}</div>}

      <div className="row">
        <button className="btn" onClick={runPreview} type="button">
          Preview matches
        </button>
        {preview !== null && (
          <span className="muted text-sm">
            {preview < 0
              ? "preview failed"
              : `${preview} signals match right now`}
          </span>
        )}
        <div className="spacer" />
        <button
          className="btn btn-primary"
          onClick={submit}
          disabled={busy || name.trim().length < 2}
          type="button"
        >
          {busy ? "Creating…" : "Create radar"}
        </button>
      </div>
    </>
  );
}
