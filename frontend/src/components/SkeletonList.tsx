"use client";

import { SignalCardSkeleton } from "@/components/SignalCard";

interface SkeletonListProps {
  /** Number of skeleton cards to render. Defaults to 3. */
  count?: number;
}

/**
 * Renders `count` shimmer placeholders that match the height and rhythm of
 * a real SignalCard. Drop this in wherever a list of signals is loading.
 */
export function SkeletonList({ count = 3 }: SkeletonListProps) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <SignalCardSkeleton key={i} />
      ))}
    </>
  );
}
