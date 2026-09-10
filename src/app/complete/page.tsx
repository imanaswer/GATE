"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Me, type Result } from "@/lib/api";

export default function Complete() {
  const router = useRouter();
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const me = await api<Me>("/me");
        if (!me.attempt) return router.replace("/domains");
        if (me.attempt.status === "in_progress") return router.replace("/arena");
        setResult(await api<Result>(`/attempts/${me.attempt.id}/result`));
      } catch (e) {
        setError(
          e instanceof ApiError && e.status === 401
            ? "Your session expired. Please sign in again."
            : "We could not load your result. Your exam is submitted — please reload.",
        );
      }
    })();
  }, [router]);

  if (error) {
    return (
      <Shell>
        <p role="alert" className="text-center text-sm text-danger">
          {error}
        </p>
      </Shell>
    );
  }

  if (!result) {
    return (
      <Shell>
        <div className="h-56 animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />
      </Shell>
    );
  }

  const minutes = result.duration_seconds ? Math.round(result.duration_seconds / 60) : null;
  const pct = result.total ? Math.round((result.score / result.total) * 100) : 0;

  return (
    <Shell>
      {result.score > 0 && <Confetti />}
      <div className="rise">
        <h1 className="text-3xl font-bold tracking-tight">That&rsquo;s a wrap.</h1>
        <p className="mt-2 text-sm text-muted">
          {result.status === "expired"
            ? "Time ran out, so your exam was submitted automatically and scored."
            : "Your exam is submitted and scored."}
        </p>

        <div className="my-8 rounded-2xl bg-surface p-8 ring-1 ring-line">
          <p className="text-xs text-muted">Your score</p>
          {/* The number counts up once. It is the only moment on this screen
              worth animating, and it lands before a student can look away. */}
          <p className="mt-1 mb-4 flex items-baseline gap-2">
            <CountUp to={result.score} className="tally text-7xl font-bold text-accent" />
            <span className="text-2xl text-muted">/ {result.total}</span>
          </p>
          <div
            className="h-1.5 overflow-hidden rounded-full bg-surface-2"
            role="img"
            aria-label={`${pct} percent correct`}
          >
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-1000 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-3 text-sm text-muted">{result.domain_name}</p>

          <dl className="mt-7 grid grid-cols-3 gap-3 border-t border-line pt-6">
            {[
              ["Correct", result.correct, "text-ok"],
              ["Wrong", result.wrong, "text-danger"],
              ["Skipped", result.skipped, "text-muted"],
            ].map(([label, value, tone]) => (
              <div key={label as string}>
                <dt className="text-xs text-muted">{label}</dt>
                <dd className={`tally mt-1 text-2xl font-bold ${tone}`}>{value}</dd>
              </div>
            ))}
          </dl>
          {minutes !== null && (
            <p className="mt-5 text-xs text-muted">
              Completed in {minutes} minute{minutes === 1 ? "" : "s"}
            </p>
          )}
        </div>

        <div className="rounded-2xl bg-surface p-6 ring-1 ring-line">
          <p className="text-xs text-muted">Certificate</p>
          <p className="mt-2 text-sm text-ok">\u2713 Issued and valid</p>
          <p className="mt-3 break-all font-mono text-sm">{result.certificate_id}</p>
          <div className="mt-5 flex flex-col gap-2 sm:flex-row">
            {/* A plain link, not a fetch-and-blob: the browser already knows how
                to download a PDF, and this one works with the tab closed. */}
            <a
              href={`/api/v1/certificates/${result.certificate_id}/pdf`}
              className="btn flex-1 px-4 py-2.5 text-center text-sm"
            >
              Download certificate
            </a>
            <a
              href={`/verify/${result.certificate_id}`}
              className="flex-1 rounded-xl border border-line px-4 py-2.5 text-sm font-semibold"
            >
              Verify
            </a>
          </div>
          <p className="mt-4 text-xs text-muted">
            Keep this ID. Anyone can confirm your certificate at the verify link.
          </p>
        </div>

        <p className="mt-8 text-center text-xs text-muted">
          You can close this page. Your result is saved.
        </p>
      </div>
    </Shell>
  );
}

/** One burst of brand-coloured confetti over the result. Positions are derived
 *  from the index, not Math.random, so server and client render the same DOM. */
function Confetti() {
  const COLOURS = ["#e8000f", "#004282", "#febc2e"];
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 overflow-hidden">
      {Array.from({ length: 28 }, (_, i) => (
        <span
          key={i}
          className="confetti"
          style={{
            left: `${(i * 37) % 100}%`,
            background: COLOURS[i % 3],
            animationDelay: `${(i * 53) % 700}ms`,
            width: i % 4 === 0 ? 12 : 8,
            height: i % 3 === 0 ? 8 : 14,
          }}
        />
      ))}
    </div>
  );
}

/** Counts from zero to the final score once, then stops. Respects
 *  prefers-reduced-motion by landing on the value immediately. */
function CountUp({ to, className }: { to: number; className?: string }) {
  const [value, setValue] = useState(0);
  const frame = useRef(0);

  useEffect(() => {
    // Set on the next frame rather than synchronously in the effect body: a
    // sync setState here cascades a render, and starting from 0 on the server
    // keeps hydration matching.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || to === 0) {
      frame.current = requestAnimationFrame(() => setValue(to));
      return () => cancelAnimationFrame(frame.current);
    }
    const start = performance.now();
    const DURATION = 900;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION);
      // Ease-out cubic: fast off the mark, settles onto the number.
      setValue(Math.round(to * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [to]);

  return (
    <span className={className} aria-label={String(to)}>
      <span aria-hidden="true">{value}</span>
    </span>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 justify-center px-6 py-12">
      <div className="w-full max-w-md">{children}</div>
    </main>
  );
}
