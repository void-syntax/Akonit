"use client";

import { useEffect, useRef, useState } from "react";

export interface FilterOption {
  value: string;
  label: string;
}

export type FilterSelectProps =
  | {
      label: string;
      /** Single-select (string or nothing). */
      value: string | null;
      onChange: (next: string | null) => void;
      options: FilterOption[];
      allLabel: string;
      /** Free-text search box; essential once the list is long. */
      searchable?: boolean;
    }
  | {
      label: string;
      /** Multi-select (list of values). */
      value: string[];
      onChange: (next: string[]) => void;
      options: FilterOption[];
      allLabel: string;
      /** Free-text search box; essential once the list is long. */
      searchable?: boolean;
    };

function isMultiProps(
  props: FilterSelectProps,
): props is Extract<FilterSelectProps, { value: string[] }> {
  return Array.isArray(props.value);
}

/**
 * One filter dropdown, used by every feed in the app.
 *
 * A native <select> can only pick a single value, but countries, sources and
 * tags are naturally multi-select, so this is a button plus a checkbox list. It
 * stays a real button and a real list, which keeps it keyboard reachable without
 * pulling in a popover library.
 */
export function FilterSelect(props: FilterSelectProps) {
  const { label, options, allLabel, searchable = true } = props;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const selected = Array.isArray(props.value) ? props.value : props.value ? [props.value] : [];

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
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle(option: string) {
    if (isMultiProps(props)) {
      const next = selected.includes(option)
        ? selected.filter((v) => v !== option)
        : [...selected, option];
      props.onChange(next);
    } else {
      props.onChange(props.value === option ? null : option);
      setOpen(false);
    }
  }

  function clear() {
    if (isMultiProps(props)) props.onChange([]);
    else props.onChange(null);
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
        ref={buttonRef}
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
        <div
          className="filter-menu"
          role="listbox"
          aria-label={label}
          ref={menuRef}
          onKeyDown={(event) => {
            const menu = menuRef.current;
            if (!menu) return;
            const options = Array.from(
              menu.querySelectorAll<HTMLButtonElement>('[role="option"]'),
            );
            if (options.length === 0) return;
            const current = document.activeElement as HTMLElement | null;
            const currentIndex = current ? options.indexOf(current as HTMLButtonElement) : -1;

            if (event.key === "ArrowDown") {
              event.preventDefault();
              const next =
                currentIndex < 0
                  ? 0
                  : Math.min(options.length - 1, currentIndex + 1);
              options[next]?.focus();
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              const prev =
                currentIndex <= 0
                  ? currentIndex < 0
                    ? options.length - 1
                    : 0
                  : currentIndex - 1;
              options[prev]?.focus();
            } else if (event.key === "Home") {
              event.preventDefault();
              options[0]?.focus();
            } else if (event.key === "End") {
              event.preventDefault();
              options[options.length - 1]?.focus();
            } else if (event.key === "Enter" && currentIndex >= 0) {
              event.preventDefault();
              options[currentIndex]?.click();
            } else if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
              buttonRef.current?.focus();
            }
          }}
        >
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
