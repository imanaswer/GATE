"use client";

import type { Question } from "@/lib/api";
import { bandFor } from "./ProgressRail";

const DIFFICULTY_TONE = {
  easy: "border-ok/40 text-ok",
  medium: "border-warn/40 text-warn",
  hard: "border-danger/40 text-danger",
} as const;

const TYPE_LABEL = {
  mcq: "MULTIPLE CHOICE",
  code_output: "CODE OUTPUT",
  debug: "DEBUG",
  scenario: "SCENARIO",
  logic: "LOGIC",
} as const;

export function QuestionCard({
  question,
  total,
  selected,
  onSelect,
}: {
  question: Question;
  total: number;
  selected: string | null;
  onSelect: (optionId: string | null) => void;
}) {
  const band = bandFor(question.position);

  return (
    <article key={question.position} className="rise">
      <header className="mb-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-bold tracking-widest text-accent">
            ⚡ CHALLENGE {String(question.position).padStart(2, "0")} / {total}
          </span>
          <span className="rounded-md border border-line px-2 py-0.5 font-mono text-[10px] tracking-widest text-muted">
            {band.label}
          </span>
          <span
            className={`rounded-md border px-2 py-0.5 font-mono text-[10px] tracking-widest ${DIFFICULTY_TONE[question.difficulty]}`}
          >
            {question.difficulty.toUpperCase()}
          </span>
          <span className="rounded-md border border-line px-2 py-0.5 font-mono text-[10px] tracking-widest text-muted">
            {TYPE_LABEL[question.type]}
          </span>
        </div>
        <h2 className="text-lg leading-relaxed font-medium text-balance">{question.body}</h2>
      </header>

      {question.code && (
        // Wide code scrolls inside its own container so the page never scrolls
        // sideways on a phone.
        <pre className="mb-5 overflow-x-auto rounded-xl border border-line bg-base p-4 text-sm leading-relaxed">
          <code className="font-mono">{question.code}</code>
        </pre>
      )}

      <fieldset>
        <legend className="sr-only">Select your answer for challenge {question.position}</legend>
        <ul className="space-y-2.5">
          {question.options.map((option, i) => {
            const isSelected = selected === option.id;
            return (
              <li key={option.id}>
                <label
                  className={[
                    "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors",
                    isSelected
                      ? "border-accent bg-accent/10"
                      : "border-line bg-surface hover:border-muted",
                  ].join(" ")}
                >
                  <input
                    type="radio"
                    name={`q-${question.position}`}
                    value={option.id}
                    checked={isSelected}
                    onChange={() => onSelect(option.id)}
                    className="sr-only"
                  />
                  <span
                    aria-hidden="true"
                    className={[
                      "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md border font-mono text-xs",
                      isSelected
                        ? "border-accent bg-accent text-accent-ink font-bold"
                        : "border-line text-muted",
                    ].join(" ")}
                  >
                    {"ABCDE"[i]}
                  </span>
                  <span className="leading-relaxed">{option.body}</span>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>

      {selected && (
        <button
          onClick={() => onSelect(null)}
          className="mt-3 text-xs text-muted underline underline-offset-4"
        >
          Clear my answer
        </button>
      )}
    </article>
  );
}
