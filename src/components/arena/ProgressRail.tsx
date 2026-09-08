"use client";

const BANDS = [
  { from: 1, to: 5, label: "FOUNDATION" },
  { from: 6, to: 10, label: "PROBLEM SOLVER" },
  { from: 11, to: 15, label: "FINAL" },
];

export function bandFor(position: number) {
  return BANDS.find((b) => position >= b.from && position <= b.to) ?? BANDS[0];
}

/** Every challenge is reachable in one tap, and its state is legible at a
 *  glance: answered, current, or still open. */
export function ProgressRail({
  total,
  current,
  answered,
  failed,
  onJump,
}: {
  total: number;
  current: number;
  answered: Set<number>;
  failed: Set<number>;
  onJump: (position: number) => void;
}) {
  return (
    <nav aria-label="Challenges" className="flex flex-wrap gap-1.5">
      {Array.from({ length: total }, (_, i) => i + 1).map((n) => {
        const isCurrent = n === current;
        const isAnswered = answered.has(n);
        const hasFailed = failed.has(n);
        return (
          <button
            key={n}
            onClick={() => onJump(n)}
            aria-current={isCurrent ? "step" : undefined}
            aria-label={`Challenge ${n}${
              hasFailed ? ", not saved" : isAnswered ? ", answered" : ", not answered"
            }`}
            className={[
              "size-8 rounded-lg border font-mono text-xs transition-colors",
              isCurrent
                ? "border-accent bg-accent text-accent-ink font-bold"
                : hasFailed
                  ? "border-danger/60 bg-danger/10 text-danger"
                  : isAnswered
                    ? "border-ok/40 bg-ok/10 text-ok"
                    : "border-line bg-surface-2 text-muted hover:border-muted",
            ].join(" ")}
          >
            {n}
          </button>
        );
      })}
    </nav>
  );
}
