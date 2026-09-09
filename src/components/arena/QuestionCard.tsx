"use client";

import type { Question } from "@/lib/api";
import { bandFor } from "./ProgressRail";

const DIFFICULTY_TONE = {
  easy: "text-ok",
  medium: "text-warn",
  hard: "text-danger",
} as const;

const TYPE_LABEL = {
  mcq: "Multiple choice",
  code_output: "Code output",
  debug: "Debug",
  scenario: "Scenario",
  logic: "Logic",
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
      <header className="mb-7">
        {/* The numeral carries the position, so the metadata below it can be a
            quiet sentence instead of a row of competing chips. */}
        <div className="flex items-start gap-5">
          <span
            aria-hidden="true"
            className="tally shrink-0 text-6xl font-bold select-none sm:text-7xl"
            style={{ color: `color-mix(in srgb, var(--color-${band.token}) 26%, transparent)` }}
          >
            {String(question.position).padStart(2, "0")}
          </span>
          <div className="min-w-0 pt-1">
            <p className="text-xs text-muted">
              <span className="sr-only">Challenge </span>
              {question.position} of {total}
              <span className="mx-2 text-line">/</span>
              <span style={{ color: `var(--color-${band.token})` }}>{band.label}</span>
              <span className="mx-2 text-line">/</span>
              <span className={DIFFICULTY_TONE[question.difficulty]}>
                {question.difficulty}
              </span>
              <span className="mx-2 text-line">/</span>
              {TYPE_LABEL[question.type]}
            </p>
            <h2 className="mt-2 text-xl leading-snug font-semibold text-balance sm:text-2xl">
              {question.body}
            </h2>
          </div>
        </div>
      </header>

      {question.code && (
        // Wide code scrolls inside its own container so the page never scrolls
        // sideways on a phone.
        <pre className="mb-6 overflow-x-auto rounded-xl bg-surface-2 p-4 text-sm leading-relaxed">
          <code className="font-mono">{question.code}</code>
        </pre>
      )}

      <fieldset>
        <legend className="sr-only">Select your answer for challenge {question.position}</legend>
        <ul className="space-y-2.5">
          {question.options.map((option, i) => {
            const isSelected = selected === option.id;
            return (
              <li
                key={option.id}
                className="deal"
                style={{ animationDelay: `${i * 45}ms` }}
              >
                <label
                  className={[
                    "relative flex cursor-pointer items-center gap-4 overflow-hidden rounded-xl p-4 transition-all duration-150",
                    isSelected
                      ? "bg-surface-2 ring-2 ring-accent shadow-[0_12px_32px_-16px_#e8000f]"
                      : "bg-surface ring-1 ring-line hover:translate-x-1 hover:bg-surface-2 hover:ring-sky/60",
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
                    key={`${option.id}-${isSelected}`}
                    className={[
                      "keycap flex size-8 shrink-0 items-center justify-center rounded-lg font-mono text-sm transition-colors",
                      isSelected
                        ? "pop bg-accent font-bold text-accent-ink"
                        : "bg-surface-2 text-muted",
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
          className="mt-4 text-xs text-muted underline underline-offset-4 hover:text-ink"
        >
          Clear my answer
        </button>
      )}
    </article>
  );
}
