"use client";

import { use, useEffect, useState } from "react";
import { Desk } from "@/components/desk";
import type { Certificate } from "@/lib/api";

/**
 * Public. No Supabase session, no bearer token — an employer holding a printed
 * certificate has neither, and verification that requires an account verifies
 * nothing. Hits the API directly rather than through `api()` for that reason.
 */
export default function Verify({ params }: PageProps<"/verify/[certificateId]">) {
  const { certificateId } = use(params);
  const [cert, setCert] = useState<Certificate | null>(null);
  const [state, setState] = useState<"loading" | "invalid" | "error">("loading");

  useEffect(() => {
    fetch(`/api/v1/certificates/${encodeURIComponent(certificateId)}`)
      .then(async (res) => {
        if (res.ok) return setCert(await res.json());
        setState(res.status === 404 ? "invalid" : "error");
      })
      .catch(() => setState("error"));
  }, [certificateId]);

  return (
    <Desk width="max-w-md">
      <div className="rise">
        <p className="mb-8 text-center font-mono text-xs tracking-widest text-muted">
          TECH ARENA · CERTIFICATE VERIFICATION
        </p>

        {!cert && state === "loading" && (
          <div className="h-72 animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />
        )}

        {state !== "loading" && (
          <div role="alert" className="rounded-2xl border border-line bg-surface p-8 text-center">
            <p className="text-4xl" aria-hidden="true">
              {state === "invalid" ? "⚠️" : "🔌"}
            </p>
            <h1 className="mt-4 text-xl font-bold">
              {state === "invalid" ? "Not a valid certificate" : "Could not verify right now"}
            </h1>
            <p className="mt-2 text-sm text-muted">
              {state === "invalid"
                ? "No certificate matches this ID. Check it against the printed copy — the ID has no letter O, I or L, and no digit 0 or 1."
                : "Something went wrong on our side. Please try again in a moment."}
            </p>
          </div>
        )}

        {cert && (
          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
            <div className="border-b border-line bg-ok/10 px-8 py-5 text-center">
              <p className="font-semibold text-ok">✓ Valid certificate</p>
            </div>
            <div className="px-8 py-8 text-center">
              <p className="text-xs text-muted">This certifies that</p>
              <p className="mt-2 text-2xl font-bold tracking-tight">{cert.student_name}</p>
              {cert.college_name && (
                <p className="mt-1 text-sm text-muted">{cert.college_name}</p>
              )}
              <p className="mt-6 text-xs text-muted">participated in Tech Arena 2026 in</p>
              <p className="mt-1 text-lg font-semibold text-accent-soft">{cert.domain_name}</p>
            </div>
            <dl className="grid grid-cols-2 gap-px border-t border-line bg-line text-center">
              {[
                ["Certificate ID", cert.certificate_id],
                ["Issued", cert.issued_at],
                ["Check code", cert.verify_code],
              ].map(([label, value]) => (
                <div key={label} className="bg-surface px-4 py-4 last:col-span-2">
                  <dt className="text-[10px] uppercase tracking-widest text-muted">{label}</dt>
                  <dd className="mt-1 break-all font-mono text-sm">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {/* Deliberately no score: the certificate is participation, and a public
            page keyed on an ID someone may have been handed is not the place to
            publish how well they did. */}
        <p className="mt-8 text-center text-xs text-muted">
          Certificates are issued by Tech Arena and verified against our records
          in real time.
        </p>
      </div>
    </Desk>
  );
}
