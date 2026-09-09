"use client";

import { notFound } from "next/navigation";
import { useState } from "react";
import type { Question } from "@/lib/api";
import { ProgressRail, StageMeters } from "@/components/arena/ProgressRail";
import { QuestionCard } from "@/components/arena/QuestionCard";
import { SaveStatus } from "@/components/arena/SaveStatus";
import { Timer } from "@/components/arena/Timer";

/**
 * Development-only view of the exam screen with fixture data.
 *
 * The arena is the screen that matters most and it sits behind Google sign-in,
 * so without this it can only be checked by taking a real exam. Returns 404 in
 * production — it renders components with fake data and touches no API.
 */
const FIXTURES: Question[] = [
  {
    position: 4,
    type: "code_output",
    body: "What does this print?",
    code: 'const a = [1, 2, 3]\nconst b = a\nb.push(4)\nconsole.log(a.length)',
    language: "javascript",
    topic: "javascript",
    difficulty: "easy",
    options: [
      { id: "1", body: "4" },
      { id: "2", body: "3" },
      { id: "3", body: "It throws because a is const" },
      { id: "4", body: "undefined" },
    ],
    selected_option_id: null,
  },
  {
    position: 8,
    type: "scenario",
    body: "A fraud model has 95% precision and 40% recall. The business says missed fraud is far more expensive than a wasted review. What should you change?",
    code: null,
    language: null,
    topic: "evaluation",
    difficulty: "medium",
    options: [
      { id: "5", body: "Raise the decision threshold to protect precision" },
      { id: "6", body: "Lower the decision threshold to catch more fraud at the cost of precision" },
      { id: "7", body: "Retrain with fewer features" },
      { id: "8", body: "Switch the metric to accuracy" },
    ],
    selected_option_id: null,
  },
  {
    position: 13,
    type: "debug",
    body: "This memoisation cache never hits. Why?",
    code: "const cache = new Map()\nfunction get(opts) {\n  if (cache.has(opts)) return cache.get(opts)\n  const v = compute(opts)\n  cache.set(opts, v)\n  return v\n}",
    language: "javascript",
    topic: "javascript",
    difficulty: "hard",
    options: [
      { id: "9", body: "Map cannot hold objects" },
      { id: "10", body: "compute is asynchronous" },
      { id: "11", body: "Map keys on object identity, and each call passes a freshly built object" },
      { id: "12", body: "The cache is never populated" },
    ],
    selected_option_id: null,
  },
];

export default function Preview() {
  if (process.env.NODE_ENV === "production") notFound();

  const [index, setIndex] = useState(0);
  const [seconds, setSeconds] = useState(742);
  const [answers, setAnswers] = useState<Record<number, string | null>>({});
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("saved");

  const question = FIXTURES[index];
  const answered = new Set(
    Object.entries(answers).filter(([, v]) => v).map(([k]) => Number(k)),
  );

  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-base/92 backdrop-blur">
        <div className="mx-auto max-w-3xl px-5 pt-3 pb-2.5">
          <div className="mb-2.5 flex flex-wrap items-center justify-between gap-3">
            <span className="truncate text-sm font-medium">Full Stack Development</span>
            <Timer seconds={seconds} />
          </div>
          <StageMeters current={question.position} answered={answered} />
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-5 py-7">
        <QuestionCard
          question={question}
          total={15}
          selected={answers[question.position] ?? null}
          onSelect={(id) => setAnswers((a) => ({ ...a, [question.position]: id }))}
        />

        <div className="mt-6 flex min-h-6 items-center justify-end">
          <SaveStatus state={saveState} onRetry={() => setSaveState("saved")} />
        </div>

        <section className="mt-9 border-t border-line pt-6">
          <ProgressRail
            total={15}
            current={question.position}
            answered={answered}
            failed={saveState === "error" ? new Set([question.position]) : new Set()}
            onJump={() => {}}
          />
        </section>

        <section className="mt-10 rounded-xl border border-dashed border-line p-4">
          <p className="mb-3 text-sm font-medium">
            PREVIEW CONTROLS — NOT PART OF THE EXAM
          </p>
          <div className="flex flex-wrap gap-2 text-xs">
            {FIXTURES.map((q, i) => (
              <Button key={q.position} onClick={() => setIndex(i)}>
                {q.difficulty} / {q.type}
              </Button>
            ))}
            {(["saving", "saved", "error"] as const).map((s) => (
              <Button key={s} onClick={() => setSaveState(s)}>
                save: {s}
              </Button>
            ))}
            {[742, 280, 45].map((s) => (
              <Button key={s} onClick={() => setSeconds(s)}>
                timer: {Math.floor(s / 60)}m
              </Button>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function Button({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="rounded-lg border border-line bg-surface-2 px-3 py-1.5 font-mono text-muted hover:border-muted"
    >
      {children}
    </button>
  );
}
