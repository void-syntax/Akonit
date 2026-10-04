/**
 * The condition catalogue used by the radar builder.
 *
 * Kept in sync with app/api/v1/taxonomy.py: the UI reads this instead of
 * hardcoding operator and unit options.
 */

const NUMERIC = ["GT", "GTE", "LT", "LTE"];

export interface ConditionType {
  type: string;
  operators: string[];
  unit_options: string[] | null;
  description: string;
}

export const CONDITION_TYPES: ConditionType[] = [
  {
    type: "COUNTRY",
    operators: ["IN", "NOT_IN"],
    unit_options: null,
    description: "Country where the signal originates",
  },
  {
    type: "SOURCE",
    operators: ["IN", "NOT_IN"],
    unit_options: null,
    description: "Platform the signal came from",
  },
  {
    type: "TAG",
    operators: ["IN", "NOT_IN"],
    unit_options: null,
    description: "System or custom tag",
  },
  {
    type: "KEYWORD",
    operators: ["IN", "NOT_IN"],
    unit_options: null,
    description: "Text present in the title or description",
  },
  {
    type: "TEXT",
    operators: ["MATCHES", "NOT_IN"],
    unit_options: null,
    description: "Fuzzy text match",
  },
  {
    type: "GROWTH",
    operators: NUMERIC,
    unit_options: ["percent"],
    description: "Change versus the previous window",
  },
  {
    type: "VELOCITY",
    operators: NUMERIC,
    unit_options: ["percent"],
    description: "Smoothed rate of change",
  },
  {
    type: "ACTIVITY",
    operators: NUMERIC,
    unit_options: null,
    description: "Absolute activity value",
  },
  {
    type: "STRENGTH",
    operators: NUMERIC,
    unit_options: ["0-100"],
    description: "Composite strength score",
  },
  {
    type: "AGE",
    operators: ["LT", "GT", "LTE", "GTE"],
    unit_options: ["minutes", "hours", "days"],
    description: "How long the signal has existed",
  },
  {
    type: "STATUS",
    operators: ["IN", "NOT_IN"],
    unit_options: null,
    description: "Lifecycle stage",
  },
  {
    type: "CROSS_SOURCE",
    operators: NUMERIC,
    unit_options: null,
    description: "Number of independent sources",
  },
  {
    type: "PERSISTENCE",
    operators: NUMERIC,
    unit_options: null,
    description: "Consecutive windows of growth",
  },
  {
    type: "DENSITY",
    operators: NUMERIC,
    unit_options: null,
    description: "Recent signals sharing this tag",
  },
];
