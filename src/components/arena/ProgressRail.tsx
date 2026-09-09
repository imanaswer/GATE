"use client";

const BANDS = [
  { from: 1, to: 5, label: "Foundation", token: "stage-1" },
  { from: 6, to: 10, label: "Problem Solver", token: "stage-2" },
  { from: 11, to: 15, label: "Final", token: "stage-3" },
] as const;

export function bandFor(position: number) {
  return BANDS.find((b) => position >= b.from && position <= b.to) ?? BANDS[0];
}

/**
 * Three stage meters rather than fifteen identical dots. A student reads depth
 * ("I'm through Foundation, halfway through Problem Solver") without counting,
 * and every challenge is still one tap away underneath.
 */
export function StageMeters({
  current,
  answered,
}: {
  current: number;
  answered: Set<number>;
}) {
  return (
    <ol className="flex gap-1.5" aria-label="Progress through the paper">
      {BANDS.map((band) => {
        const size = band.to - band.from + 1;
        const done = Array.from({ length: size }, (_, i) => band.from + i).filter((n) =>
          answered.has(n),
        ).length;
        const active = current >= band.from && current <= band.to;
        return (
          <li key={band.label} className="flex-1">
            <div
              className="h-1 overflow-hidden rounded-full bg-surface-2"
              role="img"
              aria-label={`${band.label}: ${done} of ${size} answered`}
            >
              <div
                className="h-full rounded-full transition-[width] duration-500 ease-out"
                style={{
                  width: `${(done / size) * 100}%`,
                  background: `var(--color-${band.token})`,
                }}
              />
            </div>
            <p
              className={`mt-1.5 hidden text-[11px] transition-colors sm:block ${
                active ? "text-ink" : "text-muted"
              }`}
            >
              {band.label}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

/** Every challenge reachable in one tap, its state legible at a glance. */
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
              "size-9 rounded-lg border font-mono text-xs transition-all duration-150",
              isCurrent
                ? "scale-105 border-accent bg-accent font-bold text-accent-ink"
                : hasFailed
                  ? "border-danger/60 bg-danger/10 text-danger"
                  : isAnswered
                    ? "border-ok/40 bg-ok/10 text-ok"
                    : "border-line bg-surface-2 text-muted hover:border-muted hover:text-ink",
            ].join(" ")}
          >
            {n}
          </button>
        );
      })}
    </nav>
  );
}
