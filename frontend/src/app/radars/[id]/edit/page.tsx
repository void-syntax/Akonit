"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConditionBuilder } from "@/components/ConditionBuilder";
import { api } from "@/lib/api";
import type {
  ConditionGroup,
  Country,
  NotificationFrequency,
  Radar,
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

function toGroup(ast: ConditionGroup | undefined): ConditionGroup {
  if (!ast || !Array.isArray(ast.children)) {
    return { op: "AND", children: [], is_exclude: false };
  }
  return {
    op: ast.op ?? "AND",
    is_exclude: Boolean(ast.is_exclude),
    children: ast.children.filter(
      (child) => !("op" in child && "children" in child),
    ),
  };
}

export default function EditRadarPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [radar, setRadar] = useState<Radar | null>(null);
  const [name, setName] = useState("");
  const [emoji, setEmoji] = useState("");
  const [conditions, setConditions] = useState<ConditionGroup>({
    op: "AND",
    children: [],
    is_exclude: false,
  });
  const [threshold, setThreshold] = useState(0);
  const [frequency, setFrequency] =
    useState<NotificationFrequency>("INSTANT");
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [list, c, s, t] = await Promise.all([
          api.radars(),
          api.countries(undefined, true),
          api.sources(),
          api.tags(),
        ]);
        setCountries(c);
        setSources(s.filter((item) => item.status !== "OFFLINE"));
        setTags(t);

        const found = list.find((item) => item.id === params.id);
        if (!found) return;
        setRadar(found);
        setName(found.name);
        setEmoji(found.emoji ?? "\u{1F3AF}");
        setThreshold(found.signal_threshold);
        setFrequency(found.notification_frequency);

        const stored = await api.radarConditions(params.id);
        setConditions(toGroup(stored.ast));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load radar");
      }
    })();
  }, [params.id]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.updateRadar(params.id, {
        name,
        emoji,
        conditions,
        signal_threshold: threshold,
        notification_frequency: frequency,
      });
      router.push(`/radars/${params.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save radar");
    } finally {
      setBusy(false);
    }
  }

  if (!radar) {
    return (
      <div className="empty">
        <div className="empty-title">Radar unavailable</div>
        {error && <p className="empty-text">{error}</p>}
        <Link className="btn" href="/radars">
          Back to radars
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="row" style={{ marginBottom: "var(--s4)" }}>
        <Link className="btn btn-sm btn-ghost" href={`/radars/${radar.id}`}>
          ← Back
        </Link>
      </div>

      <div className="section-title">Edit {radar.name}</div>

      <div className="panel">
        <div className="grid-2" style={{ marginBottom: "var(--s3)" }}>
          <div className="field">
            <label className="field-label" htmlFor="ename">
              Radar name
            </label>
            <input
              id="ename"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="eemoji">
              Emoji
            </label>
            <input
              id="eemoji"
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

      <div className="panel">
        <div className="section-title" style={{ marginTop: 0 }}>
          Notification &amp; threshold
        </div>

        <div className="grid-2">
          <div className="field">
            <label className="field-label" htmlFor="efreq">
              Frequency
            </label>
            <select
              id="efreq"
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
            <label className="field-label" htmlFor="ethr">
              Signal strength threshold
            </label>
            <div className="slider-row">
              <input
                id="ethr"
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
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="row">
        <div className="spacer" />
        <button
          className="btn btn-primary"
          onClick={save}
          disabled={busy || name.trim().length < 2}
          type="button"
        >
          {busy ? "Saving…" : "Save changes"}
        </button>
      </div>
    </>
  );
}