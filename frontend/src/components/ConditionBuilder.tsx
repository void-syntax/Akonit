"use client";

import { useMemo } from "react";

import type {
  Condition,
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
}

const TYPES: { value: ConditionType; label: string }[] = [
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

const NUMERIC: ConditionType[] = ["GROWTH", "ACTIVITY", "STRENGTH"];
const LIST_TYPES: ConditionType[] = [
  "COUNTRY",
  "SOURCE",
  "TAG",
  "KEYWORD",
  "STATUS",
];

function isGroup(item: ConditionGroup | Condition): item is ConditionGroup {
  return "op" in item && "children" in item;
}

function newCondition(type: ConditionType): Condition {
  switch (type) {
    case "GROWTH":
      return { type, operator: "GT", value: 100 };
    case "AGE":
      return { type, operator: "LT", value: 24, unit: "hours" };
    case "ACTIVITY":
      return { type, operator: "GT", value: 1000 };
    case "STRENGTH":
      return { type, operator: "GT", value: 50 };
    case "STATUS":
      return { type, operator: "IN", value: ["RISING", "BREAKOUT"] };
    default:
      return { type, operator: "IN", value: [] };
  }
}

export function ConditionBuilder({
  value,
  onChange,
  countries,
  sources,
  tags,
}: Props) {
  function addCondition(type: ConditionType) {
    onChange({ ...value, children: [...value.children, newCondition(type)] });
  }

  function updateCondition(index: number, next: Condition) {
    onChange({
      ...value,
      children: value.children.map((c, i) => (i === index ? next : c)),
    });
  }

  function removeCondition(index: number) {
    onChange({
      ...value,
      children: value.children.filter((_, i) => i !== index),
    });
  }

  const countryOptions = useMemo(() => countries.slice(0, 120), [countries]);

  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="join-pill">WHEN</span>
        <span className="muted" style={{ fontSize: "0.84rem" }}>
          signals match
        </span>
        <div className="spacer" />
        <span className="join-pill">
          <button
            onClick={() => onChange({ ...value, op: "AND" })}
            style={{ color: value.op === "AND" ? "var(--accent)" : undefined }}
          >
            AND
          </button>
          <span className="dim">/</span>
          <button
            onClick={() => onChange({ ...value, op: "OR" })}
            style={{ color: value.op === "OR" ? "var(--accent)" : undefined }}
          >
            OR
          </button>
        </span>
      </div>

      <div className="builder-group">
        {value.children.length === 0 && (
          <p className="dim" style={{ margin: "4px 0 10px", fontSize: "0.84rem" }}>
            No conditions yet — add countries, sources, tags or a growth threshold.
          </p>
        )}

        {value.children.map((child, index) =>
          isGroup(child) ? (
            <div key={`g${index}`} className="muted" style={{ padding: "7px 0" }}>
              nested group ({child.op})
            </div>
          ) : (
            <ConditionRow
              key={`c${index}`}
              condition={child}
              position={index}
              onChange={(next) => updateCondition(index, next)}
              onRemove={() => removeCondition(index)}
              countries={countryOptions}
              sources={sources}
              tags={tags}
            />
          ),
        )}
      </div>

      <span className="field-label">Add condition</span>
      <div className="row" style={{ marginTop: 8 }}>
        {TYPES.map((t) => (
          <button
            key={t.value}
            className="btn btn-sm"
            onClick={() => addCondition(t.value)}
          >
            + {t.label}
          </button>
        ))}
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        <span className="join-pill" style={{ borderColor: "rgba(255,77,94,0.4)" }}>
          <button
            onClick={() => onChange({ ...value, is_exclude: !value.is_exclude })}
          >
            {value.is_exclude ? "EXCLUDE ON" : "EXCLUDE OFF"}
          </button>
        </span>
        <span className="dim" style={{ fontSize: "0.76rem" }}>
          {value.is_exclude
            ? "Signals matching these conditions will be rejected."
            : "Turn this on to use the group as an exclusion rule."}
        </span>
      </div>
    </div>
  );
}

function MultiSelect({
  value,
  onChange,
  children,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  children: React.ReactNode;
}) {
  return (
    <select
      className="field"
      multiple
      size={4}
      value={value}
      onChange={(e) =>
        onChange(Array.from(e.target.selectedOptions).map((o) => o.value))
      }
    >
      {children}
    </select>
  );
}

function ConditionRow({
  condition,
  position,
  onChange,
  onRemove,
  countries,
  sources,
  tags,
}: {
  condition: Condition;
  position: number;
  onChange: (next: Condition) => void;
  onRemove: () => void;
  countries: Country[];
  sources: SourceInfo[];
  tags: Tag[];
}) {
  const isList = LIST_TYPES.includes(condition.type);
  const isNumeric = NUMERIC.includes(condition.type);
  const listValue = Array.isArray(condition.value)
    ? (condition.value as string[])
    : [];

  const patch = (next: Partial<Condition>) => onChange({ ...condition, ...next });

  return (
    <div className="builder-row">
      <span className="join-pill">
        {position === 0 ? "IF" : condition.operator === "NOT_IN" ? "EXCL" : "AND"}
      </span>

      <select
        className="field"
        value={condition.type}
        onChange={(e) => onChange(newCondition(e.target.value as ConditionType))}
        style={{ maxWidth: 150 }}
      >
        {TYPES.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>

      <select
        className="field"
        value={condition.operator}
        onChange={(e) =>
          patch({ operator: e.target.value as Condition["operator"] })
        }
        style={{ maxWidth: 140 }}
      >
        <option value="IN">is one of</option>
        <option value="NOT_IN">is NOT one of</option>
        <option value="GT">is greater than</option>
        <option value="LT">is less than</option>
      </select>

      {isList && condition.type === "COUNTRY" && (
        <MultiSelect value={listValue} onChange={(v) => patch({ value: v })}>
          {countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.flag} {c.name}
            </option>
          ))}
        </MultiSelect>
      )}

      {isList && condition.type === "SOURCE" && (
        <MultiSelect value={listValue} onChange={(v) => patch({ value: v })}>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </MultiSelect>
      )}

      {isList && condition.type === "TAG" && (
        <MultiSelect value={listValue} onChange={(v) => patch({ value: v })}>
          {tags.map((t) => (
            <option key={t.slug} value={t.slug}>
              {t.emoji} {t.name}
            </option>
          ))}
        </MultiSelect>
      )}

      {isList && condition.type === "STATUS" && (
        <MultiSelect value={listValue} onChange={(v) => patch({ value: v })}>
          {["NEW", "RISING", "BREAKOUT", "FADING"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </MultiSelect>
      )}

      {condition.type === "KEYWORD" && (
        <input
          className="field"
          placeholder="comma separated keywords"
          value={listValue.join(", ")}
          onChange={(e) =>
            patch({
              value: e.target.value
                .split(",")
                .map((v) => v.trim())
                .filter(Boolean),
            })
          }
        />
      )}

      {isNumeric && (
        <input
          className="field"
          type="number"
          value={String(condition.value ?? "")}
          onChange={(e) => patch({ value: Number(e.target.value) || 0 })}
          style={{ maxWidth: 110 }}
        />
      )}

      {condition.type === "AGE" && (
        <>
          <input
            className="field"
            type="number"
            value={String(condition.value ?? "")}
            onChange={(e) => patch({ value: Number(e.target.value) || 0 })}
            style={{ maxWidth: 100 }}
          />
          <select
            className="field"
            value={condition.unit ?? "hours"}
            onChange={(e) => patch({ unit: e.target.value })}
            style={{ maxWidth: 110 }}
          >
            <option value="minutes">minutes</option>
            <option value="hours">hours</option>
            <option value="days">days</option>
          </select>
        </>
      )}

      <button className="btn btn-sm btn-icon" onClick={onRemove} aria-label="Remove">
        ✕
      </button>
    </div>
  );
}
