"use client";

import { useEffect, useRef } from "react";

import { CloseIcon, TrashIcon } from "@/components/icons";
import { CustomTagEditor } from "@/components/CustomTagEditor";
import type { CustomTag, CustomTagDraft, Country, SourceInfo } from "@/lib/types";

export const NEW_TAG: CustomTagDraft = {
  name: "",
  keywords: [],
  aliases: [],
  hashtags: [],
  country_codes: [],
  source_ids: [],
  excludes: [],
  exclude_hashtags: [],
  exclude_countries: [],
  emoji: "",
};

export function tagToDraft(tag: CustomTag): CustomTagDraft {
  return {
    name: tag.name,
    keywords: tag.keywords,
    aliases: tag.aliases,
    hashtags: tag.hashtags,
    country_codes: tag.country_codes,
    source_ids: tag.source_ids,
    excludes: tag.excludes,
    exclude_hashtags: tag.exclude_hashtags,
    exclude_countries: tag.exclude_countries,
    emoji: tag.emoji,
  };
}

export function TagList({
  tags,
  onEdit,
  onDelete,
}: {
  tags: CustomTag[];
  onEdit: (tag: CustomTag) => void;
  onDelete: (id: string) => void;
}) {
  if (tags.length === 0) {
    return (
      <p className="dim text-sm">
        No custom tags yet. Create one to add your own categories on top of the
        built-in taxonomy.
      </p>
    );
  }

  return (
    <div className="stack-sm">
      {tags.map((tag) => (
        <div className="rule" key={tag.id}>
          <div className="rule-head">
            <strong>
              {tag.emoji} {tag.name}
            </strong>
            <span className="dim text-xs">/{tag.slug}</span>
            <div className="spacer" />
            <button className="btn btn-sm" onClick={() => onEdit(tag)} type="button">
              Edit
            </button>
            <button
              className="btn btn-sm btn-danger btn-icon"
              onClick={() => onDelete(tag.id)}
              type="button"
              aria-label={`Delete ${tag.name}`}
            >
              <TrashIcon size={13} />
            </button>
          </div>
          <div className="card-tags" style={{ marginBottom: 0 }}>
            {[
              ...tag.keywords.map((k) => `kw: ${k}`),
              ...tag.aliases.map((a) => `alias: ${a}`),
              ...tag.hashtags.map((h) => `#${h}`),
              ...tag.excludes.map((e) => `− ${e}`),
              ...tag.exclude_hashtags.map((h) => `− #${h}`),
              ...tag.exclude_countries.map((c) => `− ${c}`),
            ]
              .slice(0, 10)
              .map((label) => (
                <span className="tag-chip" key={label}>
                  {label}
                </span>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function TagSheet({
  draft,
  onChange,
  onClose,
  onSave,
  countries,
  sources,
  saving,
}: {
  draft: CustomTagDraft;
  onChange: (next: CustomTagDraft) => void;
  onClose: () => void;
  onSave: () => void;
  countries: Country[];
  sources: SourceInfo[];
  saving: boolean;
}) {
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocus.current = (document.activeElement as HTMLElement) ?? null;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus.current?.focus?.();
    };
  }, [onClose]);

  return (
    <div
      className="sheet-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="tag-sheet-title"
    >
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          <span className="sheet-title" id="tag-sheet-title">Custom tag</span>
          <div className="spacer" />
          <button
            className="btn btn-sm btn-icon"
            onClick={onClose}
            aria-label="Close"
            type="button"
          >
            <CloseIcon size={15} />
          </button>
        </div>

        <CustomTagEditor
          draft={draft}
          onChange={onChange}
          countries={countries}
          sources={sources}
        />

        <div className="row" style={{ marginTop: "var(--s3)" }}>
          <div className="spacer" />
          <button className="btn" onClick={onClose} type="button">
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={onSave}
            disabled={saving || draft.name.trim().length < 2}
            type="button"
          >
            {saving ? "Saving…" : "Save tag"}
          </button>
        </div>
      </div>
    </div>
  );
}