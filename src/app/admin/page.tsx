"use client";

import { useEffect, useState } from "react";
import { adminApi, type AdminMe, type Overview } from "@/lib/adminApi";

export default function AdminOverview() {
  const [data, setData] = useState<Overview | null>(null);
  const [me, setMe] = useState<AdminMe | null>(null);
  const [sweeping, setSweeping] = useState(false);
  const [swept, setSwept] = useState<string | null>(null);

  const load = () => adminApi<Overview>("/overview").then(setData).catch(() => {});

  useEffect(() => {
    adminApi<AdminMe>("/me").then(setMe).catch(() => {});
    load();
    const timer = setInterval(load, 30_000);
    return () => clearInterval(timer);
  }, []);

  if (!data) return <div className="h-64 animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />;

  return (
    <>
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Overview</h1>
        {/* Recomputed on read once a minute, so this is a freshness note, not
            a warning about a cron that may or may not be running. */}
        <p className="text-xs text-muted">
          Counters as of{" "}
          {data.stale_seconds < 90
            ? "under a minute ago"
            : `${Math.round(data.stale_seconds / 60)} minutes ago`}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Students", data.students],
          ["Registered", data.registered],
          ["In progress", data.in_progress],
          ["Submitted", data.submitted],
          ["Timed out", data.expired],
          ["Certificates", data.certificates],
          ["Colleges", data.colleges],
          ["Flagged", data.flagged],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded-2xl border border-line bg-surface p-4">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="mt-1 font-mono text-2xl font-bold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      {me?.role === "admin" && data.in_progress > 0 && (
        <div className="mt-6 flex flex-wrap items-center gap-3 rounded-2xl bg-surface p-4 ring-1 ring-line">
          <p className="text-sm">
            <span className="font-mono font-bold">{data.in_progress}</span> exam
            {data.in_progress === 1 ? " is" : "s are"} still open.
            <span className="ml-1 text-muted">
              Anyone past their time is scored the moment they reload; this
              finalises the ones who never came back.
            </span>
          </p>
          <button
            disabled={sweeping}
            onClick={async () => {
              setSweeping(true);
              try {
                const r = await adminApi<{ swept: number }>(
                  "/attempts/finalise-abandoned",
                  { method: "POST" },
                );
                setSwept(
                  r.swept === 0
                    ? "Nothing to finalise — every open exam is still within its time."
                    : `Finalised and certificated ${r.swept} attempt${r.swept === 1 ? "" : "s"}.`,
                );
                await load();
              } finally {
                setSweeping(false);
              }
            }}
            className="ml-auto rounded-xl border border-line px-3 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {sweeping ? "Finalising…" : "Finalise abandoned"}
          </button>
        </div>
      )}
      {swept && (
        <p role="status" className="mt-3 text-sm text-ok">
          {swept}
        </p>
      )}

      <p className="mt-6 text-sm text-muted">
        Average score:{" "}
        <span className="font-mono font-semibold text-fg">
          {data.average_score ?? "—"}
        </span>{" "}
        / 15
      </p>

      <h2 className="mt-8 mb-3 text-sm font-semibold">By domain</h2>
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[420px] text-left text-sm">
          <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
            <tr>
              <th scope="col" className="px-4 py-2">Domain</th>
              <th scope="col" className="px-4 py-2 text-right">Completed</th>
              <th scope="col" className="px-4 py-2 text-right">Average</th>
            </tr>
          </thead>
          <tbody>
            {data.by_domain.map((d) => (
              <tr key={d.slug} className="border-t border-line">
                <td className="px-4 py-2">{d.name}</td>
                <td className="px-4 py-2 text-right font-mono tabular-nums">{d.attempts}</td>
                <td className="px-4 py-2 text-right font-mono tabular-nums">
                  {d.average_score ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
