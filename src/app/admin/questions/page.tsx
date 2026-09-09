"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { adminApi, type AdminMe, type AdminQuestion } from "@/lib/adminApi";

type Page = { total: number; page: number; pages: number; questions: AdminQuestion[] };

export default function Questions() {
  const [q, setQ] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);
  const [me, setMe] = useState<AdminMe | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page) });
    if (q) params.set("q", q);
    if (difficulty) params.set("difficulty", difficulty);
    if (status) params.set("status", status);
    return adminApi<Page>(`/questions?${params}`).then(setData);
  }, [q, difficulty, status, page]);

  useEffect(() => {
    adminApi<AdminMe>("/me").then(setMe).catch(() => {});
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const canWrite = me?.role === "admin";

  async function upload(file: File) {
    setNotice("Importing…");
    try {
      const res = await adminApi<{ ok: boolean; created?: number; updated?: number; errors?: string[] }>(
        "/questions/import",
        { method: "POST", body: await file.text() },
      );
      setNotice(
        res.ok
          ? `Imported: ${res.created} created, ${res.updated} updated.`
          : `Rejected — nothing was changed. First problems: ${res.errors?.slice(0, 3).join("; ")}`,
      );
      await load();
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Import failed.");
    }
  }

  async function retire(id: string) {
    await adminApi(`/questions/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">
          Questions{data && <span className="ml-2 text-sm font-normal text-muted">{data.total}</span>}
        </h1>
        {canWrite && (
          <label className="cursor-pointer rounded-xl border border-line px-3 py-2 text-sm font-semibold">
            Import CSV
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void upload(file);
                e.target.value = "";
              }}
            />
          </label>
        )}
      </div>

      {notice && (
        <p role="status" className="mb-4 rounded-xl border border-line bg-surface px-4 py-2 text-sm">
          {notice}
        </p>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => {
            setPage(1);
            setQ(e.target.value);
          }}
          placeholder="Search question text or topic"
          aria-label="Search questions"
          className="min-w-56 flex-1 rounded-xl border border-line bg-surface px-3 py-2 text-sm"
        />
        {[
          [difficulty, setDifficulty, "Any difficulty", ["easy", "medium", "hard"]],
          [status, setStatus, "Any status", ["draft", "active", "retired"]],
        ].map(([value, set, label, options], i) => (
          <select
            key={i}
            value={value as string}
            onChange={(e) => {
              setPage(1);
              (set as (v: string) => void)(e.target.value);
            }}
            aria-label={label as string}
            className="rounded-xl border border-line bg-surface px-3 py-2 text-sm"
          >
            <option value="">{label as string}</option>
            {(options as string[]).map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        ))}
      </div>

      <ul className="space-y-3">
        {data?.questions.map((question) => (
          <li key={question.id} className="rounded-2xl border border-line bg-surface p-4">
            <div className="flex flex-wrap items-baseline gap-2 text-xs text-muted">
              <span className="font-mono text-accent-soft">{question.domain_slug}</span>
              <span>{question.topic}</span>
              <span>{question.difficulty}</span>
              <span>{question.type}</span>
              <span
                className={question.status === "active" ? "text-ok" : "text-muted"}
              >
                {question.status}
              </span>
              {canWrite && question.status !== "retired" && (
                <button
                  onClick={() => void retire(question.id)}
                  className="ml-auto underline underline-offset-2 hover:text-danger"
                >
                  Retire
                </button>
              )}
            </div>
            <p className="mt-2 text-sm">{question.body}</p>
            {question.code && (
              <pre className="mt-2 overflow-x-auto rounded-xl bg-surface-2 p-3 text-xs">
                <code>{question.code}</code>
              </pre>
            )}
            <ul className="mt-2 space-y-1 text-sm">
              {question.options.map((o) => (
                <li key={o.id} className={o.is_correct ? "text-ok" : "text-muted"}>
                  {o.is_correct ? "✓" : "·"} {o.body}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>

      {data && data.pages > 1 && (
        <div className="mt-6 flex items-center gap-3 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-xl border border-line px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-muted">
            Page {data.page} of {data.pages}
          </span>
          <button
            disabled={page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-xl border border-line px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}
