"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { CustomTag } from "@/lib/types";
import { useAuth } from "@/store/auth";

function split(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

const EMPTY_FORM = {
  name: "",
  keywords: "",
  hashtags: "",
  country_codes: "",
  source_ids: "",
  excludes: "",
};

const FIELDS = [
  {
    id: "ctkw",
    label: "Keywords (comma separated)",
    key: "keywords" as const,
    placeholder: "korean makeup, k-beauty, glass skin",
  },
  { id: "ctht", label: "Hashtags", key: "hashtags" as const, placeholder: "#kbeauty, #glassskin" },
  { id: "ctex", label: "Excludes", key: "excludes" as const, placeholder: "cosplay" },
  { id: "ctcc", label: "Countries (codes)", key: "country_codes" as const, placeholder: "KR, JP" },
  { id: "ctsrc", label: "Sources (ids)", key: "source_ids" as const, placeholder: "tiktok, youtube" },
];

export default function ProfilePage() {
  const { email, logout } = useAuth();
  const [customTags, setCustomTags] = useState<CustomTag[]>([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setCustomTags(await api.customTags());
    } catch {
      setCustomTags([]);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function createTag() {
    if (form.name.trim().length < 2) return;
    setBusy(true);
    try {
      await api.createCustomTag({
        name: form.name,
        keywords: split(form.keywords),
        hashtags: split(form.hashtags),
        country_codes: split(form.country_codes).map((c) => c.toUpperCase()),
        source_ids: split(form.source_ids),
        excludes: split(form.excludes),
      });
      setForm(EMPTY_FORM);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-title">PROFILE</div>

      <div className="card">
        <div className="row">
          <span className="badge badge-meta">{email ?? "not signed in"}</span>
          <div className="spacer" />
          <Link className="btn btn-sm" href="/settings">
            Settings
          </Link>
          <button className="btn btn-sm" onClick={logout}>
            Sign out
          </button>
        </div>
      </div>

      <div className="section-title">CUSTOM TAGS</div>
      <p className="muted" style={{ fontSize: "0.85rem", marginTop: -4 }}>
        Create your own tags. They really affect matching — no code required.
      </p>

      <div className="builder">
        <div className="stack">
          <div>
            <label className="field-label" htmlFor="ctname">
              Name
            </label>
            <input
              id="ctname"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Korean Makeup"
            />
          </div>

          {FIELDS.map((field) => (
            <div key={field.id}>
              <label className="field-label" htmlFor={field.id}>
                {field.label}
              </label>
              <input
                id={field.id}
                value={form[field.key]}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                placeholder={field.placeholder}
              />
            </div>
          ))}

          <button
            className="btn btn-primary"
            onClick={createTag}
            disabled={busy || form.name.trim().length < 2}
          >
            {busy ? "Saving…" : "Create custom tag"}
          </button>
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        {customTags.length === 0 && (
          <p className="dim" style={{ fontSize: "0.84rem" }}>
            No custom tags yet.
          </p>
        )}
        {customTags.map((tag) => (
          <div key={tag.id} className="card">
            <div className="row">
              <span className="badge badge-meta">
                {tag.emoji ?? "🏷️"} {tag.name}
              </span>
              <div className="spacer" />
              <button
                className="btn btn-sm btn-icon"
                onClick={async () => {
                  await api.deleteCustomTag(tag.id);
                  await load();
                }}
                aria-label="Delete"
              >
                ✕
              </button>
            </div>
            {tag.keywords.length > 0 && (
              <div className="card-tags" style={{ marginTop: 8 }}>
                {tag.keywords.map((keyword) => (
                  <span key={keyword} className="tag-chip">
                    {keyword}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}