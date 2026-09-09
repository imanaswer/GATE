"use client";

/** A display of the server's clock, not a clock. The exam ends when the server
 *  says so; this only tells the student how long they have. */
export function Timer({ seconds }: { seconds: number | null }) {
  if (seconds === null) return null;

  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const tone =
    seconds <= 60 ? "text-danger" : seconds <= 300 ? "text-warn" : "text-ink";
  const label = `${minutes} minute${minutes === 1 ? "" : "s"} and ${secs} second${secs === 1 ? "" : "s"} remaining`;

  return (
    <div className="flex items-baseline gap-2">
      <span
        className={`font-mono text-xl font-bold tabular-nums transition-colors sm:text-2xl ${tone} ${
          // Under a minute the timer earns the attention; before that it must
          // not pull focus away from the question.
          seconds <= 60 ? "animate-pulse" : ""
        }`}
        // Announce at one-minute granularity: a per-second live region would
        // make a screen reader unusable.
        aria-label={label}
        role="timer"
      >
        {String(minutes).padStart(2, "0")}:{String(secs).padStart(2, "0")}
      </span>
      <span className="sr-only" aria-live="polite">
        {secs === 0 ? label : ""}
      </span>
    </div>
  );
}
