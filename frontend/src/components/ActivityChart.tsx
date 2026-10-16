"use client";

import { useMemo } from "react";

import { compact, timeAgo } from "@/lib/format";

interface Point {
  t: string;
  activity: number;
}

export function ActivityChart({ points }: { points: Point[] }) {
  const width = 640;
  const height = 140;

  const coords = useMemo(() => {
    if (points.length < 2) return [];
    const values = points.map((p) => p.activity);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    return values.map((value, index) => ({
      x: (index / (values.length - 1)) * width,
      y: height - ((value - min) / span) * (height - 24) - 12,
    }));
  }, [points]);

  if (coords.length < 2) {
    return (
      <p className="dim text-sm">
        Collecting history — the chart appears after the second snapshot.
      </p>
    );
  }

  const line = coords
    .map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`)
    .join(" ");
  const area = `${line} ${width},${height} 0,${height}`;
  const peak = Math.max(...points.map((p) => p.activity));
  const first = points[0];
  const last = points[points.length - 1];
  const summary = `Activity history across ${points.length} snapshots: from ${first.activity} at ${first.t} to ${last.activity} now; peak ${peak}.`;

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart"
        role="img"
        aria-label="Activity history"
        aria-describedby="activity-chart-summary"
      >
        <title>Activity history</title>
        <desc id="activity-chart-summary">{summary}</desc>
        <polygon points={area} className="chart-area" />
        <polyline points={line} className="chart-line" />
        {coords.map((c, index) => (
          <circle key={index} cx={c.x} cy={c.y} r={3} className="chart-dot" />
        ))}
      </svg>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="dim text-xs">{timeAgo(points[0].t)}</span>
        <span className="dim text-xs">peak {compact(peak)}</span>
        <span className="dim text-xs">now</span>
      </div>
    </div>
  );
}