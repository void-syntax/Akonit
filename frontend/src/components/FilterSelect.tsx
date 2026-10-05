"use client";

import { useEffect, useRef, useState } from "react";

export interface FilterOption {
  value: string;
  label: string;
}

interface Props {
  label: string;
  /** A string for single-select, a list for multi-select. */
  value: string | string[] | null;
  onChange: (next: never) => void;
  options: FilterOption[];
  allLabel: string;
  /** Free-text search box; essential once the list is long. */
  searchable?: boolean;
}

/**
 * One filter dropdown, used by every feed in the app.
 *
 * A native <select> can only pick a single value, but countries, sources and
 * tags are naturally multi-select, so this is a button plus a checkbox list. It
 * stays a real button and a real list, which keeps it keyboard reachable without
 * pulling in a popover library.
 */
export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
  searchable = true,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement>(null);

  const isMulti = Array.isArray(value);
  const selected = Array.isArray(value) ? value : value ? [value] : [];

  // A menu left open behind a route change or an outside click would trap the
  // pointer, so both close it.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (root.current && !root.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle(option: string) {
    if (isMulti) {
      const next = selected.includes(option)
        ? selected.filter((v) => v !== option)
        : [...selected, option];
      (onChange as (v: string[]) => void)(next);
    } else {
      (onChange as (v: string | null) => void)(
        value === option ? null : option,
      );
      setOpen(false);
    }
  }

  function clear() {
    if (isMulti) (onChange as (v: string[]) => void)([]);
    else (onChange as (v: string | null) => void)(null);
  }

  const needle = query.trim().toLowerCase();
  const visible = needle
    ? options.filter((o) => o.label.toLowerCase().includes(needle))
    : options;

  const caption =
    selected.length === 0
      ? allLabel
      : selected.length === 1
        ? (options.find((o) => o.value === selected[0])?.label ?? selected[0])
        : `${selected.length} selected`;

  return (
    <div className="filter-group" ref={root}>
      <button
        type="button"
        className="filter"
        data-active={selected.length > 0}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="filter-label">{label}</span>
        {caption}
        <span className={`filter-caret${open ? " is-open" : ""}`} aria-hidden="true" />
      </button>

      {open && (
        <div className="filter-menu" role="listbox" aria-label={label}>
          {searchable && options.length > 8 && (
            <input
              className="filter-menu-search"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${label.toLowerCase()}…`}
              autoFocus
            />
          )}

          <button
            type="button"
            className="filter-menu-item filter-menu-clear"
            onClick={clear}
            disabled={selected.length === 0}
          >
            {allLabel}
          </button>

          {visible.length === 0 && (
            <div className="filter-menu-empty">Nothing matches “{query}”</div>
          )}

          {visible.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={selected.includes(option.value)}
              className="filter-menu-item"
              data-active={selected.includes(option.value)}
              onClick={() => toggle(option.value)}
            >
              <span className="filter-menu-check" aria-hidden="true">
                {selected.includes(option.value) ? "✓" : ""}
              </span>
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
