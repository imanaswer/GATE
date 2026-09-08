"use client";

import { useEffect, useState } from "react";
import { adminApi, type Overview } from "@/lib/adminApi";

export default function AdminOverview() {
  const [data, setData] = useState<Overview | null>(null);

  useEffect(() => {
    const load = () => adminApi<Overview>("/overview").then(setData).catch(() => {});
    load();
    const timer = setInterval(load, 30_000);
    return () => clearInterval(timer);
  }, []);

  if (!data) return <div className="h-64 animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />;

  return (
    <>
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Overview</h1>
        {/* Counters are refreshed by a one-minute cron, so say how old they are
            rather than implying they are live. */}
        <p className="text-xs text-muted">
          Counters refreshed {data.stale_seconds < 90 ? "under a minute" : `${Math.round(data.stale_seconds / 60)} minutes`} ago
          {data.stale_seconds > 300 && " — the refresh cron may not be running"}
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
