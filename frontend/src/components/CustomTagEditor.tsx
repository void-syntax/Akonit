"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { countryName, sourceName } from "@/lib/format";
import type { CustomTagDraft, Country, SourceInfo } from "@/lib/types";

const FIELDS: {
  key: keyof CustomTagDraft;
  label: string;
  hint: string;
  placeholder: string;
}[] = [
  {
    key: "keywords",
    label: "Keywords",
    hint: "Comma separated. A signal matches if any keyword appears.",
    placeholder: "lipstick, kbeauty, serum",
  },
  {
    key: "aliases",
    label: "Aliases",
    hint: "Synonyms — matched exactly like keywords.",
    placeholder: "makeup, cosmetics",
  },
  {
    key: "hashtags",
    label: "Hashtags",
    hint: "With or without #. The # is stripped automatically.",
    placeholder: "#kbeauty, #koreanmakeup",
  },
  {
    key: "excludes",
    label: "Exclude words",
    hint: "If any of these appear, the signal is rejected.",
    placeholder: "giveaway, discount",
  },
  {
    key: "exclude_hashtags",
    label: "Exclude hashtags",
    hint: "Signals carrying these hashtags are rejected.",
    placeholder: "#ad, #sponsored",
  },
];

interface Props {
  draft: CustomTagDraft;
  onChange: (next: CustomTagDraft) => void;
  countries: Country[];
  sources: SourceInfo[];
}

export function CustomTagEditor({ draft, onChange, countries, sources }: Props) {
  const [preview, setPreview] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  function setList(key: keyof CustomTagDraft, text: string) {
    onChange({
      ...draft,
      [key]: text
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean),
    });
  }

  function toggleInList(key: keyof CustomTagDraft, value: string) {
    const current = (draft[key] as string[]) ?? [];
    onChange({
      ...draft,
      [key]: current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value],
    });
  }

  async function runPreview() {
    setBusy(true);
    setPreview(null);
    try {
      const result = await api.customTagPreview(draft);
      setPreview(result.matched);
    } catch {
      setPreview(-1);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="builder">
      <div className="builder-head">
        <span className="join-pill">CUSTOM TAG</span>
        <div className="spacer" />
        <button className="btn btn-sm" onClick={runPreview} disabled={busy} type="button">
          {busy ? "Checking…" : "Preview matches"}
        </button>
        {preview !== null && (
          <span className="badge badge-accent">
            {preview < 0 ? "preview failed" : `${preview} signals match now`}
          </span>
        )}
      </div>

      <div className="builder-body">
        <div className="grid-2">
          <div className="field">
            <label className="field-label" htmlFor="ct-name">
              Tag name
            </label>
            <input
              id="ct-name"
              value={draft.name}
              onChange={(e) => onChange({ ...draft, name: e.target.value })}
              placeholder="Korea Makeup"
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="ct-emoji">
              Emoji
            </label>
            <input
              id="ct-emoji"
              value={draft.emoji ?? ""}
              onChange={(e) => onChange({ ...draft, emoji: e.target.value })}
              maxLength={4}
              placeholder="💄"
            />
          </div>
        </div>

        {FIELDS.map((field) => (
          <div className="field" key={field.key}>
            <label className="field-label" htmlFor={`ct-${field.key}`}>
              {field.label}
            </label>
            <input
              id={`ct-${field.key}`}
              value={(draft[field.key] as string[]).join(", ")}
              onChange={(e) => setList(field.key, e.target.value)}
              placeholder={field.placeholder}
            />
            <div className="field-hint">{field.hint}</div>
          </div>
        ))}

        <div className="field">
          <span className="field-label">Only these countries</span>
          <div className="chip-picker">
            {countries.map((c) => (
              <button
                key={c.code}
                type="button"
                className="chip"
                data-active={draft.country_codes.includes(c.code)}
                onClick={() => toggleInList("country_codes", c.code)}
              >
                {c.flag} {countryName(c.code)}
              </button>
            ))}
          </div>
          <div className="field-hint">Leave empty to match every country.</div>
        </div>

        <div className="field">
          <span className="field-label">Exclude countries</span>
          <div className="chip-picker">
            {countries.map((c) => (
              <button
                key={c.code}
                type="button"
                className="chip"
                data-active={draft.exclude_countries.includes(c.code)}
                onClick={() => toggleInList("exclude_countries", c.code)}
              >
                {c.flag} {countryName(c.code)}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <span className="field-label">Only these sources</span>
          <div className="chip-picker">
            {sources.map((s) => (
              <button
                key={s.id}
                type="button"
                className="chip"
                data-active={draft.source_ids.includes(s.id)}
                onClick={() => toggleInList("source_ids", s.id)}
              >
                {sourceName(s.id)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}