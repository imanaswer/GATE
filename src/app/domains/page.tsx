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
      <div className="mb-10 text-center">
        <p className="mb-3 font-mono text-xs tracking-widest text-accent">STEP 3 / 4</p>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Select your challenge
        </h1>
        <p className="mt-3 text-sm text-muted">
          15 challenges, 20 minutes, one attempt. Choose the domain you know best.
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
                className="group h-full w-full rounded-2xl border border-line bg-surface p-5 text-left transition-[transform,border-color] duration-150 hover:-translate-y-0.5 hover:border-accent focus-visible:border-accent disabled:opacity-50 disabled:hover:translate-y-0"
              >
                <span className="mb-3 block text-2xl" aria-hidden="true">
                  {d.icon}
                </span>
                <span className="block font-semibold">{d.name}</span>
                <span className="mt-1 block text-sm leading-snug text-muted">
                  {d.description}
                </span>
                <span className="mt-3 block font-mono text-[10px] tracking-widest text-accent opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                  {selected === d.slug ? "OPENING…" : "ENTER →"}
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
