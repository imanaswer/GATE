"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Domain, type Paper } from "@/lib/api";

export default function Briefing({ params }: PageProps<"/briefing/[slug]">) {
  const { slug } = use(params);
  const router = useRouter();
  const [domain, setDomain] = useState<Domain | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Domain[]>("/domains")
      .then((list) => {
        const found = list.find((d) => d.slug === slug);
        if (!found) router.replace("/domains");
        else setDomain(found);
      })
      .catch(() => setError("We could not load this challenge. Please go back and retry."));
  }, [slug, router]);

  async function begin() {
    setStarting(true);
    setError(null);
    try {
      await api<Paper>("/attempts", { method: "POST", json: { domain_slug: slug } });
      router.replace("/arena");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // They already have an attempt. Not an error worth alarming them over.
        return router.replace("/complete");
      }
      setError(
        e instanceof ApiError
          ? e.message
          : "We could not start your exam. Check your connection and try again.",
      );
      setStarting(false);
    }
  }

  return (
    <main className="flex flex-1 justify-center px-6 py-12">
      <div className="w-full max-w-lg">
        <div className="rise rounded-2xl border border-line bg-surface p-7">
          <p className="mb-3 font-mono text-xs tracking-widest text-accent">
            MISSION BRIEFING
          </p>
          <h1 className="flex items-center gap-3 text-2xl font-bold">
            <span aria-hidden="true">{domain?.icon}</span>
            {domain?.name ?? "Loading…"}
          </h1>

          <dl className="my-7 grid grid-cols-3 gap-3 text-center">
            {[
              ["15", "challenges"],
              ["20", "minutes"],
              ["1", "attempt"],
            ].map(([value, label]) => (
              <div key={label} className="rounded-xl border border-line bg-surface-2 py-4">
                <dt className="sr-only">{label}</dt>
                <dd>
                  <span className="block font-mono text-2xl font-bold text-accent">
                    {value}
                  </span>
                  <span className="mt-1 block text-xs text-muted">{label}</span>
                </dd>
              </div>
            ))}
          </dl>

          <h2 className="mb-3 text-sm font-semibold">Before you start</h2>
          <ul className="space-y-2.5 text-sm text-muted">
            {[
              "The timer runs on our server. Closing this page will not pause it.",
              "Every answer saves as you go. A refresh or a dropped connection puts you back where you were.",
              "You can move between challenges and change any answer until you submit.",
              "When the time runs out your exam is submitted automatically and still scored.",
              "Leaving the tab is recorded and shown to the organisers. It does not disqualify you.",
            ].map((line) => (
              <li key={line} className="flex gap-2.5">
                <span aria-hidden="true" className="mt-1.5 size-1 shrink-0 rounded-full bg-accent" />
                {line}
              </li>
            ))}
          </ul>

          {error && (
            <p role="alert" className="mt-5 text-sm text-danger">
              {error}
            </p>
          )}

          <button
            onClick={begin}
            disabled={starting || !domain}
            className="mt-7 w-full rounded-xl bg-accent px-6 py-4 font-semibold text-accent-ink transition-transform duration-150 hover:-translate-y-0.5 active:translate-y-0 disabled:cursor-wait disabled:opacity-60 disabled:hover:translate-y-0"
          >
            {starting ? "Starting your exam…" : "Start — the timer begins now"}
          </button>
          <p className="mt-3 text-center text-xs text-muted">
            This is your one attempt. It cannot be restarted.
          </p>
        </div>

        <button
          onClick={() => router.push("/domains")}
          disabled={starting}
          className="mt-4 w-full py-2 text-center text-sm text-muted underline underline-offset-4 disabled:opacity-40"
        >
          Choose a different domain
        </button>
      </div>
    </main>
  );
}
