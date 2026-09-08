"use client";

import { useEffect, useState } from "react";
import { adminApi, type CollegeStat, type QuestionStat } from "@/lib/adminApi";

export default function Analytics() {
  const [questions, setQuestions] = useState<QuestionStat[] | null>(null);
  const [colleges, setColleges] = useState<CollegeStat[] | null>(null);

  useEffect(() => {
    adminApi<{ questions: QuestionStat[] }>("/analytics/questions?limit=50")
      .then((r) => setQuestions(r.questions))
      .catch(() => setQuestions([]));
    adminApi<{ colleges: CollegeStat[] }>("/analytics/colleges")
      .then((r) => setColleges(r.colleges))
      .catch(() => setColleges([]));
  }, []);

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>

      <h2 className="mt-8 mb-2 text-sm font-semibold">Worst-answered questions</h2>
      <p className="mb-3 text-xs text-muted">
        A question nearly everyone gets wrong is usually a broken question rather
        than a hard one, and one everyone gets right is measuring nothing. The
        rate counts only questions students actually attempted — a high skip
        count is a separate signal, usually that the question reads as
        unanswerable. Both want a human to look before the next event.
      </p>
      {!questions ? (
        <div className="h-40 animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />
      ) : questions.length === 0 ? (
        <p className="text-sm text-muted">Nothing answered yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-line">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
              <tr>
                {["Question", "Domain", "Difficulty", "Answered", "Skipped", "Correct rate", "Avg time"].map((h) => (
                  <th key={h} scope="col" className="px-4 py-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {questions.map((q) => (
                <tr key={q.id} className="border-t border-line">
                  <td className="max-w-md px-4 py-2">{q.body}</td>
                  <td className="px-4 py-2 font-mono text-xs text-muted">{q.domain_slug}</td>
                  <td className="px-4 py-2 text-muted">{q.difficulty}</td>
                  <td className="px-4 py-2 font-mono tabular-nums">{q.answered}</td>
                  <td className="px-4 py-2 font-mono tabular-nums text-muted">{q.skipped}</td>
                  <td
                    className={`px-4 py-2 font-mono tabular-nums ${
                      (q.correct_rate ?? 1) < 0.15 ? "text-danger" : ""
                    }`}
                  >
                    {q.correct_rate === null ? "—" : `${Math.round(q.correct_rate * 100)}%`}
                  </td>
                  <td className="px-4 py-2 font-mono tabular-nums text-muted">
                    {q.avg_ms ? `${Math.round(q.avg_ms / 1000)}s` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="mt-10 mb-3 text-sm font-semibold">Colleges</h2>
      {!colleges ? (
        <div className="h-40 animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-line">
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
              <tr>
                {["College", "City", "Students", "Completed", "Average"].map((h) => (
                  <th key={h} scope="col" className="px-4 py-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {colleges.map((c) => (
                <tr key={c.id} className="border-t border-line">
                  <td className="px-4 py-2">{c.name}</td>
                  <td className="px-4 py-2 text-muted">{c.city ?? "—"}</td>
                  <td className="px-4 py-2 font-mono tabular-nums">{c.students}</td>
                  <td className="px-4 py-2 font-mono tabular-nums">{c.completed}</td>
                  <td className="px-4 py-2 font-mono tabular-nums">{c.average_score ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
