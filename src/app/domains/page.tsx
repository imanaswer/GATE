"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Domain, type Me } from "@/lib/api";

export default function Domains() {
  const router = useRouter();
  const [domains, setDomains] = useState<Domain[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [me, list] = await Promise.all([api<Me>("/me"), api<Domain[]>("/domains")]);
        if (cancelled) return;
        // Send people where they actually belong rather than showing a choice
        // they cannot make.
        if (!me.profile.registered) return router.replace("/register");
        if (me.attempt?.status === "in_progress") return router.replace("/arena");
        if (me.attempt) return router.replace("/complete");
        setDomains(list);
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiError && e.status === 401
              ? "Your session expired. Please sign in again."
              : "We could not load the challenges. Check your connection and reload.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (error) {
    return (
      <Shell>
        <p role="alert" className="text-center text-sm text-danger">
          {error}
        </p>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mb-9">
        <p className="mb-2 text-xs text-muted">Step 3 of 4</p>
        <h1 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
          Which arena?
        </h1>
        <p className="mt-2 max-w-md text-muted">
          You get one attempt, so pick the domain you know best. The questions
          are drawn fresh for you either way.
        </p>
      </div>

      {!domains ? (
        <ul className="grid gap-3 sm:grid-cols-2" aria-busy="true" aria-label="Loading challenges">
          {[...Array(5)].map((_, i) => (
            <li key={i} className="h-28 animate-pulse rounded-2xl bg-surface-2" />
          ))}
        </ul>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {domains.map((d, i) => (
            <li key={d.id} className="rise" style={{ animationDelay: `${i * 45}ms` }}>
              <button
                onClick={() => {
                  setSelected(d.slug);
                  router.push(`/briefing/${d.slug}`);
                }}
                disabled={selected !== null}
                aria-label={`${d.name}. ${d.description ?? ""}`}
                className="group h-full w-full rounded-2xl bg-surface p-5 text-left ring-1 ring-line transition-[transform,box-shadow] duration-150 hover:-translate-y-1 hover:ring-accent focus-visible:ring-accent disabled:opacity-50 disabled:hover:translate-y-0"
              >
                <span className="mb-3 block text-3xl" aria-hidden="true">
                  {d.icon}
                </span>
                <span className="block text-lg font-semibold">{d.name}</span>
                <span className="mt-1 block text-sm leading-snug text-muted">
                  {d.description}
                </span>
                <span className="mt-4 flex items-center gap-1.5 text-sm font-medium text-accent">
                  {selected === d.slug ? "Opening" : "Enter"}
                  <span
                    aria-hidden="true"
                    className="transition-transform duration-150 group-hover:translate-x-1"
                  >
                    →
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 justify-center px-6 py-12">
      <div className="w-full max-w-2xl">{children}</div>
    </main>
  );
}
