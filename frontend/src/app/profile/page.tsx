"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { NEW_TAG, TagList, TagSheet, tagToDraft } from "@/components/TagManager";
import { PlusIcon } from "@/components/icons";
import { api } from "@/lib/api";
import type {
  Country,
  CustomTag,
  CustomTagDraft,
  SourceInfo,
} from "@/lib/types";
import { useAuth } from "@/store/auth";

export default function ProfilePage() {
  const { email, loading: authLoading } = useAuth();
  const [tags, setTags] = useState<CustomTag[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [editing, setEditing] = useState<CustomTag | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<CustomTagDraft>(NEW_TAG);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!email) return;
    void (async () => {
      try {
        setTags(await api.customTags());
        const [c, s] = await Promise.all([
          api.countries(undefined, true),
          api.sources(),
        ]);
        setCountries(c);
        setSources(s.filter((item) => item.status !== "OFFLINE"));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load tags");
      }
    })();
  }, [email]);

  function startCreate() {
    setEditing(null);
    setDraft(NEW_TAG);
    setOpen(true);
  }

  function startEdit(tag: CustomTag) {
    setEditing(tag);
    setDraft(tagToDraft(tag));
    setOpen(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        await api.updateCustomTag(editing.id, draft);
      } else {
        await api.createCustomTag(draft);
      }
      setTags(await api.customTags());
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save tag");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this custom tag?")) return;
    try {
      await api.deleteCustomTag(id);
      setTags(await api.customTags());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete tag");
    }
  }

  if (authLoading) return <p className="muted">Loading…</p>;

  if (!email) {
    return (
      <div className="empty">
        <div className="empty-title">Cannot reach the local API</div>
        <p className="empty-text">
          Custom tags, radars and notifications live in your local database.
          Start the collector with <code className="mono">docker compose up</code>{" "}
          and reload.
        </p>
        <button className="btn btn-primary" onClick={() => location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="section-title">
        Custom tags
        <div className="spacer" />
        <button className="btn btn-sm btn-primary" onClick={startCreate} type="button">
          <PlusIcon size={13} /> New tag
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <TagList tags={tags} onEdit={startEdit} onDelete={remove} />

      {open && (
        <TagSheet
          draft={draft}
          onChange={setDraft}
          onClose={() => setOpen(false)}
          onSave={save}
          countries={countries}
          sources={sources}
          saving={saving}
        />
      )}

      <div className="section-title">Account</div>
      <div className="panel">
        <div className="row">
          <span className="muted text-sm">Signed in as</span>
          <strong>{email}</strong>
        </div>
        <div className="row" style={{ marginTop: "var(--s3)" }}>
          <Link className="btn" href="/settings">
            Notification &amp; theme settings
          </Link>
          <Link className="btn btn-ghost" href="/radars">
            My radars
          </Link>
        </div>
      </div>
    </>
  );
}