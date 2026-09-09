"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Result } from "@/lib/api";
import { useExam } from "@/lib/useExam";
import { ProgressRail, StageMeters } from "@/components/arena/ProgressRail";
import { QuestionCard } from "@/components/arena/QuestionCard";
import { SaveStatus } from "@/components/arena/SaveStatus";
import { Timer } from "@/components/arena/Timer";

export default function Arena() {
  const router = useRouter();
  const [position, setPosition] = useState(1);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const exam = useExam();
  const { attempt, markShown, logEvent, remaining, finished } = exam;

  useEffect(() => {
    if (exam.loadError === "NO_ATTEMPT") router.replace("/domains");
    if (exam.loadError === "UNAUTHENTICATED") router.replace("/");
    if (finished) router.replace("/complete");
  }, [exam.loadError, finished, router]);

  useEffect(() => markShown(), [position, markShown]);

  // Keyboard: A–E (or 1–5) picks an option, ←/→ moves between challenges.
  // Ignored while typing or while the submit dialog is open.
  useEffect(() => {
    if (!attempt || confirming) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      const total = exam.questions.length;
      if (e.key === "ArrowRight") return setPosition((p) => Math.min(total, p + 1));
      if (e.key === "ArrowLeft") return setPosition((p) => Math.max(1, p - 1));
      const k = e.key.toUpperCase();
      const idx = "ABCDE".indexOf(k) >= 0 ? "ABCDE".indexOf(k) : "12345".indexOf(k);
      const option = exam.questions.find((q) => q.position === position)?.options[idx];
      if (option) exam.answer(position, option.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [attempt, confirming, position, exam]);

  // Integrity signals. Recorded and shown to organisers; they never end an
  // attempt on their own. See the design doc §1.2 for what this can and
  // cannot actually detect — which is much less than it appears.
  useEffect(() => {
    if (!attempt) return;
    const onVisibility = () => {
      if (document.visibilityState === "hidden") logEvent("tab_switch");
    };
    const onFullscreen = () => {
      if (!document.fullscreenElement) logEvent("fullscreen_exit");
    };
    const onOffline = () => logEvent("disconnect");
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("fullscreenchange", onFullscreen);
    window.addEventListener("offline", onOffline);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("fullscreenchange", onFullscreen);
      window.removeEventListener("offline", onOffline);
    };
  }, [attempt, logEvent]);

  useEffect(() => {
    if (!attempt) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [attempt]);

  const doSubmit = useCallback(async () => {
    if (!attempt || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api<Result>(`/attempts/${attempt.id}/submit`, { method: "POST" });
      router.replace("/complete");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) return router.replace("/complete");
      setSubmitError("We could not submit. Check your connection and try again.");
      setSubmitting(false);
      setConfirming(false);
    }
  }, [attempt, submitting, router]);

  // At 00:00 the student just goes to their result. The server has already
  // expired and scored the attempt — the client never submits on its behalf,
  // which is why this is a navigation and not a chain of callbacks.
  useEffect(() => {
    if (remaining === 0) router.replace("/complete");
  }, [remaining, router]);

  if (exam.loading || !attempt) {
    return (
      <main className="flex flex-1 items-center justify-center px-6">
        <p className="font-mono text-xs tracking-widest text-muted" aria-busy="true">
          LOADING YOUR ARENA…
        </p>
      </main>
    );
  }

  const question = exam.questions.find((q) => q.position === position)!;
  const total = exam.questions.length;
  const answered = new Set(
    Object.entries(exam.answers).filter(([, v]) => v).map(([k]) => Number(k)),
  );
  const failed = new Set(
    Object.entries(exam.saveState).filter(([, v]) => v === "error").map(([k]) => Number(k)),
  );

  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-base/92 backdrop-blur">
        <div className="mx-auto max-w-3xl px-5 pt-3 pb-2.5">
          <div className="mb-2.5 flex flex-wrap items-center justify-between gap-3">
            <span className="truncate text-sm font-medium">{attempt.domain_name}</span>
            <Timer seconds={exam.remaining} />
          </div>
          {/* Three stage meters, not one flat bar: depth through the paper is
              what a student actually wants to know, and it costs the same row. */}
          <StageMeters current={position} answered={answered} />
        </div>
      </header>

      {exam.offline && (
        <p
          role="status"
          className="bg-warn/15 px-5 py-2 text-center text-sm text-warn"
        >
          You are offline. Your answers are kept and will save when you reconnect.
        </p>
      )}

      <main className="mx-auto w-full max-w-3xl flex-1 px-5 py-7">
        <QuestionCard
          question={question}
          total={total}
          selected={exam.answers[position] ?? null}
          onSelect={(optionId) => exam.answer(position, optionId)}
        />

        <div className="mt-6 flex min-h-6 items-center justify-end">
          <SaveStatus state={exam.saveState[position]} onRetry={() => exam.retry(position)} />
        </div>

        <div className="mt-6 flex items-center justify-between gap-3">
          <button
            onClick={() => setPosition((p) => Math.max(1, p - 1))}
            disabled={position === 1}
            className="rounded-xl border border-line bg-surface px-5 py-3 text-sm font-medium disabled:opacity-30"
          >
            ← Previous
          </button>
          {position < total ? (
            <button
              onClick={() => setPosition((p) => Math.min(total, p + 1))}
              className="btn px-6 py-3"
            >
              Next →
            </button>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="btn px-6 py-3"
            >
              Review & submit
            </button>
          )}
        </div>

        <section className="mt-9 border-t border-line pt-6">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-medium">All challenges</h2>
            <p className="text-xs text-muted">
              {answered.size} of {total} answered
            </p>
          </div>
          <ProgressRail
            total={total}
            current={position}
            answered={answered}
            failed={failed}
            onJump={setPosition}
          />
          {position !== total && (
            <button
              onClick={() => setConfirming(true)}
              className="mt-5 text-sm text-muted underline underline-offset-4"
            >
              Submit now
            </button>
          )}
          <p className="mt-5 hidden text-xs text-muted sm:block">
            Tip: press <Kbd>A</Kbd>–<Kbd>E</Kbd> to answer, <Kbd>←</Kbd> <Kbd>→</Kbd> to move.
          </p>
        </section>
      </main>

      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="submit-title"
          className="fixed inset-0 z-20 flex items-center justify-center bg-base/80 p-6 backdrop-blur-sm"
        >
          <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-6">
            <h2 id="submit-title" className="mb-2 text-lg font-semibold">
              Submit your exam?
            </h2>
            <p className="mb-1 text-sm text-muted">
              You have answered {answered.size} of {total} challenges.
            </p>
            {answered.size < total && (
              <p className="mb-1 text-sm text-warn">
                {total - answered.size} unanswered will be marked as skipped.
              </p>
            )}
            {exam.unsaved > 0 && (
              <p className="mb-1 text-sm text-danger">
                {exam.unsaved} answer{exam.unsaved === 1 ? "" : "s"} did not save. Go back
                and retry before submitting.
              </p>
            )}
            <p className="mb-5 text-sm text-muted">This cannot be undone.</p>

            {submitError && (
              <p role="alert" className="mb-4 text-sm text-danger">
                {submitError}
              </p>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => setConfirming(false)}
                disabled={submitting}
                className="flex-1 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm font-medium disabled:opacity-40"
              >
                Keep working
              </button>
              <button
                onClick={doSubmit}
                disabled={submitting}
                className="btn flex-1 px-4 py-3 text-sm"
              >
                {submitting ? "Submitting…" : "Submit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="keycap mx-0.5 inline-block rounded-md border border-line bg-surface-2 px-1.5 font-mono text-[10px] text-ink">
      {children}
    </kbd>
  );
}
