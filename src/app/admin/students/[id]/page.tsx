"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { adminApi, type StudentDetail } from "@/lib/adminApi";

export default function StudentDetailPage({
  params,
}: PageProps<"/admin/students/[id]">) {
  const { id } = use(params);
  const [s, setS] = useState<StudentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi<StudentDetail>(`/students/${id}`)
      .then(setS)
      .catch(() => setError("Could not load that student."));
  }, [id]);

  if (error) return <p role="alert" className="text-danger">{error}</p>;
  if (!s) return <div className="h-64 animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />;

  return (
    <>
      <Link href="/admin/students" className="text-sm text-muted underline underline-offset-2">
        ← All students
      </Link>
      <h1 className="mt-3 text-2xl font-bold tracking-tight">{s.name}</h1>

      <dl className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {[
          ["Email", s.email],
          ["Phone", s.phone],
          ["Student ID", s.student_id],
          ["College", s.college_name],
          ["Location", s.location],
          ["Domain", s.domain_name],
          ["Status", s.attempt_status ?? "not started"],
          ["Started", when(s.started_at)],
          ["Submitted", when(s.submitted_at)],
          ["Took", s.duration_seconds === null ? "—"
            : `${took(s.duration_seconds)}${s.attempt_status === "expired" ? " (ran out of time)" : ""}`],
          ["Certificate", s.certificate_id],
        ].map(([label, value]) => (
          <div key={label as string} className="flex gap-2 text-sm">
            <dt className="w-28 shrink-0 text-muted">{label}</dt>
            <dd className="break-all">{value ?? "—"}</dd>
          </div>
        ))}
      </dl>

      {s.attempt_id && (
        <>
          <p className="mt-6 text-sm">
            Score <span className="font-mono font-bold">{s.score}</span> ·{" "}
            {s.correct} correct · {s.wrong} wrong · {s.skipped} skipped
          </p>

          <h2 className="mt-8 mb-3 text-sm font-semibold">
            Per-question breakdown
            {/* Withheld from the student's own result page: showing it there
                publishes the answer key to everyone still to sit the exam. */}
            <span className="ml-2 font-normal text-muted">(admin only)</span>
          </h2>
          <p className="mb-3 text-xs text-muted">
            <b>Took</b> above is wall clock measured on our server. The per-question
            <b> Time</b> below is reported by the browser and is advisory — it excludes
            idle time and a determined student can fake it, so the two will not add up.
          </p>
          <div className="overflow-x-auto rounded-2xl border border-line">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
                <tr>
                  {["#", "Topic", "Difficulty", "Result", "Time"].map((h) => (
                    <th key={h} scope="col" className="px-4 py-2">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {s.questions.map((q) => (
                  <tr key={q.position} className="border-t border-line">
                    <td className="px-4 py-2 font-mono">{q.position}</td>
                    <td className="px-4 py-2">{q.topic}</td>
                    <td className="px-4 py-2 text-muted">{q.difficulty}</td>
                    <td className="px-4 py-2">
                      {q.skipped ? (
                        <span className="text-muted">skipped</span>
                      ) : q.is_correct ? (
                        <span className="text-ok">correct</span>
                      ) : (
                        <span className="text-danger">wrong</span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono tabular-nums text-muted">
                      {q.response_ms ? `${Math.round(q.response_ms / 1000)}s` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2 className="mt-8 mb-3 text-sm font-semibold">Integrity flags</h2>
      {s.flags.length === 0 ? (
        <p className="text-sm text-muted">None recorded.</p>
      ) : (
        <>
          <p className="mb-3 text-xs text-muted">
            Signals for a human to review. They never disqualify anyone
            automatically, and a browser cannot see a second device at all — see
            the design spec §1.2 for what these do and do not mean.
          </p>
          <ul className="space-y-2 text-sm">
            {s.flags.map((f, i) => (
              <li key={i} className="rounded-xl border border-line bg-surface px-4 py-2">
                <span className="font-mono text-xs text-accent-soft">{f.type}</span>
                <span className="ml-2 text-xs text-muted">
                  {new Date(f.occurred_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

/** Local time, not the raw UTC the API returns. */
function when(iso: string | null) {
  return iso ? new Date(iso).toLocaleString() : "—";
}

/** m:ss. Null while an attempt is still running. */
function took(seconds: number | null) {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  return `${m}:${String(seconds % 60).padStart(2, "0")}`;
}
