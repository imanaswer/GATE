"use client";

import type { SaveState } from "@/lib/useExam";

/** A student must always know whether their answer is safe. Silence is the one
 *  thing this must never do. */
export function SaveStatus({
  state,
  onRetry,
}: {
  state: SaveState | undefined;
  onRetry: () => void;
}) {
  if (state === "saving") {
    return <span className="text-xs text-muted">Saving…</span>;
  }
  if (state === "saved") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-ok">
        <span aria-hidden="true">✓</span> Saved
      </span>
    );
  }
  if (state === "error") {
    return (
      <span role="alert" className="flex items-center gap-2 text-xs text-danger">
        Not saved
        <button
          onClick={onRetry}
          className="rounded-md border border-danger/40 px-2 py-0.5 font-medium text-danger"
        >
          Retry
        </button>
      </span>
    );
  }
  return null;
}
