"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { adminApi, type AdminStudent } from "@/lib/adminApi";

type Filters = { q: string; domain: string; attempt_status: string };

export default function Students() {
  const [filters, setFilters] = useState<Filters>({ q: "", domain: "", attempt_status: "" });
  const [rows, setRows] = useState<AdminStudent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const query = useCallback(
    (extra?: Record<string, string>) =>
      new URLSearchParams({
        ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
        ...extra,
      }).toString(),
    [filters],
  );

  useEffect(() => {
    // Debounced so typing in the search box does not fire a query per keystroke
    // at the one moment the database is busiest. The flag is set inside the
    // callback, not the effect body — a synchronous setState there cascades.
    const timer = setTimeout(() => {
      setLoading(true);
      adminApi<{ students: AdminStudent[]; next_cursor: string | null }>(
        `/students?${query()}`,
      )
        .then((r) => {
          setRows(r.students);
          setCursor(r.next_cursor);
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  async function loadMore() {
    if (!cursor) return;
    const r = await adminApi<{ students: AdminStudent[]; next_cursor: string | null }>(
      `/students?${query({ cursor })}`,
    );
    setRows((prev) => [...prev, ...r.students]);
    setCursor(r.next_cursor);
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Students</h1>
        {/* A plain link, not a fetch: the browser streams the download itself
            and it keeps working if this tab is closed. */}
        <a
          href={`/api/v1/admin/export/csv?${query()}`}
          className="rounded-xl border border-line px-3 py-2 text-sm font-semibold"
        >
          Export CSV
        </a>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <input
          value={filters.q}
          onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
          placeholder="Name, email or student ID"
          aria-label="Search students"
          className="min-w-56 flex-1 rounded-xl border border-line bg-surface px-3 py-2 text-sm"
        />
        <select
          value={filters.attempt_status}
          onChange={(e) => setFilters((f) => ({ ...f, attempt_status: e.target.value }))}
          aria-label="Filter by attempt status"
          className="rounded-xl border border-line bg-surface px-3 py-2 text-sm"
        >
          <option value="">Any status</option>
          <option value="none">Not started</option>
          <option value="in_progress">In progress</option>
          <option value="submitted">Submitted</option>
          <option value="expired">Timed out</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
            <tr>
              {["Name", "College", "Domain", "Status", "Score", "Started", "Took", "Certificate"].map((h) => (
                <th key={h} scope="col" className="px-4 py-2">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="border-t border-line">
                <td className="px-4 py-2">
                  <Link href={`/admin/students/${s.id}`} className="font-medium underline underline-offset-2">
                    {s.name}
                  </Link>
                  <span className="block text-xs text-muted">{s.email}</span>
                </td>
                <td className="px-4 py-2 text-muted">{s.college_name ?? "—"}</td>
                <td className="px-4 py-2 text-muted">{s.domain_name ?? "—"}</td>
                <td className="px-4 py-2">{s.attempt_status ?? "not started"}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{s.score ?? "—"}</td>
                <td className="px-4 py-2 text-xs text-muted">{when(s.started_at)}</td>
                <td className="px-4 py-2 font-mono tabular-nums" title={
                  s.attempt_status === "expired" ? "Ran out of time — this is the limit, not a finish time" : undefined
                }>
                  {took(s.duration_seconds)}
                  {s.attempt_status === "expired" && <span className="ml-1 text-xs text-muted">(ran out)</span>}
                </td>
                <td className="px-4 py-2 font-mono text-xs">{s.certificate_id ?? "—"}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted">
                  No students match those filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {cursor && (
        <button
          onClick={loadMore}
          className="mt-4 rounded-xl border border-line px-4 py-2 text-sm font-semibold"
        >
          Load more
        </button>
      )}
    </>
  );
}

/** Local time, not the raw UTC the API returns — organisers read this at a
 *  glance and an ISO string is 5.5 hours wrong for them. */
function when(iso: string | null) {
  return iso ? new Date(iso).toLocaleString() : "—";
}

/** m:ss. Null while an attempt is still running. */
function took(seconds: number | null) {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  return `${m}:${String(seconds % 60).padStart(2, "0")}`;
}
