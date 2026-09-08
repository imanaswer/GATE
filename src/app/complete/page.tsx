"use client";

import { useEffect, useState } from "react";
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

  return (
    <Shell>
      <div className="rise text-center">
        <p className="mb-4 text-5xl" aria-hidden="true">
          🎉
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Mission complete</h1>
        <p className="mt-2 text-sm text-muted">
          {result.status === "expired"
            ? "Time ran out, so your exam was submitted automatically and scored."
            : "Your exam has been submitted successfully."}
        </p>

        <div className="my-8 rounded-2xl border border-line bg-surface p-8">
          <p className="font-mono text-[10px] tracking-widest text-muted">YOUR SCORE</p>
          <p className="my-2 font-mono text-6xl font-bold text-accent tabular-nums">
            {result.score}
            <span className="text-2xl text-muted"> / {result.total}</span>
          </p>
          <p className="text-sm text-muted">{result.domain_name}</p>

          <dl className="mt-7 grid grid-cols-3 gap-3 border-t border-line pt-6 text-center">
            {[
              ["Correct", result.correct, "text-ok"],
              ["Wrong", result.wrong, "text-danger"],
              ["Skipped", result.skipped, "text-muted"],
            ].map(([label, value, tone]) => (
              <div key={label as string}>
                <dt className="text-xs text-muted">{label}</dt>
                <dd className={`mt-1 font-mono text-xl font-bold ${tone}`}>{value}</dd>
              </div>
            ))}
          </dl>
          {minutes !== null && (
            <p className="mt-5 text-xs text-muted">
              Completed in {minutes} minute{minutes === 1 ? "" : "s"}
            </p>
          )}
        </div>

        <div className="rounded-2xl border border-line bg-surface p-6">
          <p className="font-mono text-[10px] tracking-widest text-muted">CERTIFICATE</p>
          <p className="mt-2 text-sm text-muted">
            Your certificate is being prepared. It will appear here shortly.
          </p>
        </div>

        <p className="mt-8 text-xs text-muted">
          You can close this page. Your result is saved.
        </p>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 justify-center px-6 py-12">
      <div className="w-full max-w-md">{children}</div>
    </main>
  );
}
