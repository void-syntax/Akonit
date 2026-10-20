"use client";

import { useMemo, useState } from "react";

import { CloseIcon, PlusIcon } from "@/components/icons";
import type {
  RadarCondition as Condition,
  ConditionGroup,
  ConditionType,
  Country,
  SourceInfo,
  Tag,
} from "@/lib/types";

interface Props {
  value: ConditionGroup;
  onChange: (next: ConditionGroup) => void;
  countries: Country[];
  sources: SourceInfo[];
  tags: Tag[];
  previewCount?: number | null;
}

type ConditionKind = ConditionType;

const KINDS: { value: ConditionKind; label: string }[] = [
  { value: "COUNTRY", label: "Country" },
  { value: "SOURCE", label: "Source" },
  { value: "TAG", label: "Tag" },
  { value: "KEYWORD", label: "Keyword" },
  { value: "GROWTH", label: "Growth" },
  { value: "ACTIVITY", label: "Activity" },
  { value: "AGE", label: "Signal age" },
  { value: "STATUS", label: "Status" },
  { value: "STRENGTH", label: "Strength" },
];

const NUMERIC_KINDS: ConditionKind[] = ["GROWTH", "ACTIVITY", "STRENGTH"];

export function makeCondition(kind: ConditionKind): Condition {
  switch (kind) {
    case "GROWTH":
      return { type: kind, operator: "GT", value: 100 };
    case "AGE":
      return { type: kind, operator: "LT", value: 24, unit: "hours" };
    case "ACTIVITY":
      return { type: kind, operator: "GT", value: 1000 };
    case "STRENGTH":
      return { type: kind, operator: "GT", value: 50 };
    case "STATUS":
      return { type: kind, operator: "IN", value: ["RISING", "BREAKOUT"] };
    default:
      return { type: kind, operator: "IN", value: [] };
  }
}

export function isGroup(item: ConditionGroup | Condition): item is ConditionGroup {
  return "op" in item && "children" in item;
}

export function listValue(condition: Condition): string[] {
  return Array.isArray(condition.value) ? (condition.value as string[]) : [];
}

export function ConditionBuilder({
  value,
  onChange,
  countries,
  sources,
  tags,
  previewCount,
}: Props) {
  const [kind, setKind] = useState<ConditionKind>("COUNTRY");
  const [countryQuery, setCountryQuery] = useState("");
  const [tagQuery, setTagQuery] = useState("");

  const children = value.children || [];
  const leaves = children.filter((c) => !isGroup(c));

  function addCondition() {
    onChange({ ...value, children: [...children, makeCondition(kind)] });
  }

  function updateCondition(index: number, next: Condition) {
    onChange({
      ...value,
      children: children.map((c, i) => (i === index ? next : c)),
    });
  }

  function removeCondition(index: number) {
    onChange({
      ...value,
      children: children.filter((_, i) => i !== index),
    });
  }

  const filteredCountries = useMemo(() => {
    const term = countryQuery.trim().toLowerCase();
    const list = term
      ? countries.filter(
          (c) =>
            c.name.toLowerCase().includes(term) ||
            c.code.toLowerCase() === term,
        )
      : countries;
    return list.slice(0, 120);
  }, [countries, countryQuery]);

  const filteredTags = useMemo(() => {
    const term = tagQuery.trim().toLowerCase();
    const list = term
      ? tags.filter(
          (t) =>
            t.name.toLowerCase().includes(term) || t.slug.includes(term),
        )
      : tags;
    return list.slice(0, 160);
  }, [tags, tagQuery]);

  return (
    <div className="builder">
      <div className="builder-head">
        <span className="join-pill">WHEN</span>
        <span className="muted text-sm">signals match</span>
        <div className="spacer" />
        <div className="logic-toggle">
          <button
            data-active={value.op === "AND"}
            onClick={() => onChange({ ...value, op: "AND" })}
            type="button"
          >
            AND
          </button>
          <button
            data-active={value.op === "OR"}
            onClick={() => onChange({ ...value, op: "OR" })}
            type="button"
          >
            OR
          </button>
        </div>
        <button
          className="chip"
          data-active={value.is_exclude}
          onClick={() => onChange({ ...value, is_exclude: !value.is_exclude })}
          type="button"
        >
          {value.is_exclude ? "EXCLUDE ON" : "EXCLUDE OFF"}
        </button>
      </div>

      <div className="builder-body">
        {leaves.length === 0 && (
          <p className="dim text-sm" style={{ marginTop: 0 }}>
            No conditions yet. Add countries, sources, tags or a growth
            threshold below.
          </p>
        )}

        {children.map((child, index) =>
          isGroup(child) ? (
            <div key={`g${index}`} className="muted text-sm">
              nested group ({child.op})
            </div>
          ) : (
            <ConditionRow
              key={`c${index}`}
              condition={child}
              position={index}
              countries={filteredCountries}
              countryQuery={countryQuery}
              onCountryQuery={setCountryQuery}
              sources={sources}
              tags={filteredTags}
              tagQuery={tagQuery}
              onTagQuery={setTagQuery}
              onChange={(next) => updateCondition(index, next)}
              onRemove={() => removeCondition(index)}
            />
          ),
        )}

        <div className="row" style={{ marginTop: "var(--s3)" }}>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as ConditionKind)}
            style={{ maxWidth: 170 }}
          >
            {KINDS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <button className="btn btn-sm" onClick={addCondition} type="button">
            <PlusIcon size={13} /> Add condition
          </button>
          {previewCount !== null && previewCount !== undefined && (
            <span className="badge badge-accent" style={{ marginLeft: "auto" }}>
              {previewCount} signals match right now
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

interface RowProps {
  condition: Condition;
  position: number;
  countries: Country[];
  countryQuery: string;
  onCountryQuery: (next: string) => void;
  sources: SourceInfo[];
  tags: Tag[];
  tagQuery: string;
  onTagQuery: (next: string) => void;
  onChange: (next: Condition) => void;
  onRemove: () => void;
}

function ConditionRow({
  condition,
  position,
  countries,
  countryQuery,
  onCountryQuery,
  sources,
  tags,
  tagQuery,
  onTagQuery,
  onChange,
  onRemove,
}: RowProps) {
  const selected = listValue(condition);
  const numeric = NUMERIC_KINDS.includes(condition.type as any);

  function toggle(value: string) {
    const next = selected.includes(value)
      ? selected.filter((v) => v !== value)
      : [...selected, value];
    onChange({ ...condition, value: next });
  }

  return (
    <div className="condition">
      <span className="rule-join">
        {position === 0
          ? "IF"
          : condition.operator === "NOT_IN"
            ? "EXCLUDE"
            : "AND"}
      </span>

      <select
        value={condition.type}
        onChange={(e) => onChange(makeCondition(e.target.value as ConditionKind))}
        style={{ maxWidth: 140 }}
      >
        {KINDS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>

      <select
        value={condition.operator}
        onChange={(e) =>
          onChange({
            ...condition,
            operator: e.target.value as Condition["operator"],
          })
        }
        style={{ maxWidth: 130 }}
      >
        <option value="IN">is any of</option>
        <option value="NOT_IN">is none of</option>
        <option value="GT">is above</option>
        <option value="LT">is below</option>
      </select>

      {condition.type === "COUNTRY" && (
        <div style={{ flex: 1, minWidth: 240 }}>
          <input
            placeholder="Search countries…"
            value={countryQuery}
            onChange={(e) => onCountryQuery(e.target.value)}
            style={{ marginBottom: 6 }}
          />
          <div className="chip-picker">
            {countries.map((c) => (
              <button
                key={c.code}
                type="button"
                className="chip"
                data-active={selected.includes(c.code)}
                onClick={() => toggle(c.code)}
              >
                {c.flag} {c.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {condition.type === "SOURCE" && (
        <div className="chip-picker" style={{ flex: 1, minWidth: 240 }}>
          {sources.map((s) => (
            <button
              key={s.id}
              type="button"
              className="chip"
              data-active={selected.includes(s.id)}
              onClick={() => toggle(s.id)}
              title={s.description ?? s.name}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {condition.type === "TAG" && (
        <div style={{ flex: 1, minWidth: 240 }}>
          <input
            placeholder="Search tags…"
            value={tagQuery}
            onChange={(e) => onTagQuery(e.target.value)}
            style={{ marginBottom: 6 }}
          />
          <div className="chip-picker">
            {tags.map((t) => (
              <button
                key={t.slug}
                type="button"
                className="chip"
                data-active={selected.includes(t.slug)}
                onClick={() => toggle(t.slug)}
              >
                {t.emoji} {t.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {condition.type === "STATUS" && (
        <div className="chip-picker" style={{ flex: 1, minWidth: 200 }}>
          {["NEW", "RISING", "BREAKOUT", "FADING"].map((s) => (
            <button
              key={s}
              type="button"
              className="chip"
              data-active={selected.includes(s)}
              onClick={() => toggle(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {condition.type === "KEYWORD" && (
        <input
          className="field"
          style={{ flex: 1, minWidth: 200 }}
          placeholder="comma separated keywords"
          value={selected.join(", ")}
          onChange={(e) =>
            onChange({
              ...condition,
              value: e.target.value
                .split(",")
                .map((v) => v.trim())
                .filter(Boolean),
            })
          }
        />
      )}

      {numeric && (
        <div className="slider-row" style={{ flex: 1, minWidth: 220 }}>
          <input
            type="range"
            min={0}
            max={condition.type === "GROWTH" ? 1000 : 100000}
            step={condition.type === "GROWTH" ? 5 : 100}
            value={Number(condition.value ?? 0)}
            onChange={(e) => onChange({ ...condition, value: Number(e.target.value) })}
          />
          <span className="slider-value">
            {Number(condition.value ?? 0)}
            {condition.type === "GROWTH" ? "%" : ""}
          </span>
        </div>
      )}

      {condition.type === "AGE" && (
        <>
          <input
            type="number"
            min={1}
            value={Number(condition.value ?? 24)}
            onChange={(e) => onChange({ ...condition, value: Number(e.target.value) })}
            style={{ maxWidth: 90 }}
          />
          <select
            value={condition.unit ?? "hours"}
            onChange={(e) => onChange({ ...condition, unit: e.target.value })}
            style={{ maxWidth: 110 }}
          >
            <option value="minutes">minutes</option>
            <option value="hours">hours</option>
            <option value="days">days</option>
          </select>
        </>
      )}

      <button
        className="btn btn-sm btn-icon"
        type="button"
        onClick={onRemove}
        aria-label="Remove condition"
      >
        <CloseIcon size={13} />
      </button>
    </div>
  );
}
