"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, ApiError, type Attempt, type Paper, type Question } from "@/lib/api";

export type SaveState = "idle" | "saving" | "saved" | "error";

/**
 * Owns the live exam: the paper, the answers, the countdown, and the autosave
 * queue. The view renders this; it does not decide any of it.
 *
 * Two things it is careful about, because both are how a student loses work:
 *  - A failed save is never silent. It retries with backoff and, if it still
 *    fails, says so and keeps the answer selected locally so a later save wins.
 *  - The countdown is a display of the server's clock, resynced from every save
 *    response. It is never the thing that decides whether time is up.
 */
function subscribeToConnection(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

export function useExam() {
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<number, string | null>>({});
  const [saveState, setSaveState] = useState<Record<number, SaveState>>({});
  const [remaining, setRemaining] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [finished, setFinished] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const offline = useSyncExternalStore(subscribeToConnection, () => !navigator.onLine, () => false);

  // Set when a question is displayed, so response_ms measures reading time
  // rather than time since page load. Zero until the first question renders.
  const shownAt = useRef(0);
  const inFlight = useRef<Record<number, AbortController>>({});
  // Retries call back into save; a ref breaks the circular reference without
  // recreating the callback on every render.
  const saveRef = useRef<(p: number, o: string | null, n?: number) => void>(() => {});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const paper = await api<Paper>("/attempts/current");
        if (cancelled) return;
        if (!paper.attempt) return setLoadError("NO_ATTEMPT");
        if (paper.finished || paper.attempt.status !== "in_progress") {
          return setFinished(true);
        }
        setAttempt(paper.attempt);
        setQuestions(paper.questions);
        setAnswers(
          Object.fromEntries(paper.questions.map((q) => [q.position, q.selected_option_id])),
        );
        setRemaining(paper.attempt.remaining_seconds);
      } catch (e) {
        if (!cancelled) {
          setLoadError(
            e instanceof ApiError && e.status === 401 ? "UNAUTHENTICATED" : "LOAD_FAILED",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Display only. The server decides when time is actually up.
  const ticking = remaining !== null && !finished;
  useEffect(() => {
    if (!ticking) return;
    const id = setInterval(
      () => setRemaining((r) => (r === null ? null : Math.max(0, r - 1))),
      1000,
    );
    return () => clearInterval(id);
  }, [ticking]);

  const save = useCallback(
    async (position: number, optionId: string | null, attemptNo = 0) => {
      if (!attempt) return;
      inFlight.current[position]?.abort();
      const controller = new AbortController();
      inFlight.current[position] = controller;

      setSaveState((s) => ({ ...s, [position]: "saving" }));
      try {
        const res = await api<{ remaining_seconds: number }>(
          `/attempts/${attempt.id}/answers/${position}`,
          {
            method: "PUT",
            json: {
              option_id: optionId,
              response_ms: shownAt.current ? Date.now() - shownAt.current : null,
            },
            sessionToken: attempt.session_token,
            signal: controller.signal,
          },
        );
        setSaveState((s) => ({ ...s, [position]: "saved" }));
        // Resync the countdown from the server on every save, so clock drift and
        // a backgrounded tab both correct themselves.
        setRemaining(res.remaining_seconds);
      } catch (e) {
        if (controller.signal.aborted) return;
        if (e instanceof ApiError && e.status === 409) return setFinished(true);
        if (attemptNo < 4) {
          // Exponential backoff with jitter: 50,000 clients retrying in lockstep
          // is how a recovering server gets knocked over again.
          const delay = 400 * 2 ** attemptNo + Math.random() * 250;
          setTimeout(() => saveRef.current(position, optionId, attemptNo + 1), delay);
          return;
        }
        setSaveState((s) => ({ ...s, [position]: "error" }));
      }
    },
    [attempt],
  );

  useEffect(() => {
    saveRef.current = save;
  }, [save]);

  const answer = useCallback(
    (position: number, optionId: string | null) => {
      setAnswers((a) => ({ ...a, [position]: optionId }));
      save(position, optionId);
    },
    [save],
  );

  const retry = useCallback(
    (position: number) => save(position, answers[position] ?? null),
    [save, answers],
  );

  const markShown = useCallback(() => {
    shownAt.current = Date.now();
  }, []);

  const logEvent = useCallback(
    (type: "tab_switch" | "fullscreen_exit" | "disconnect") => {
      if (!attempt) return;
      // Best effort. A failure here must never interrupt the exam.
      api(`/attempts/${attempt.id}/events`, {
        method: "POST",
        json: { type, detail: {} },
      }).catch(() => {});
    },
    [attempt],
  );

  const answeredCount = Object.values(answers).filter(Boolean).length;
  const unsaved = Object.entries(saveState).filter(([, v]) => v === "error").length;

  return {
    attempt,
    questions,
    answers,
    saveState,
    remaining,
    loading,
    finished,
    loadError,
    offline,
    answeredCount,
    unsaved,
    answer,
    retry,
    markShown,
    logEvent,
    setFinished,
  };
}
