"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Desk, Win } from "@/components/desk";
import { api, ApiError, type College, type Me, type Place } from "@/lib/api";

export default function Register() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [colleges, setColleges] = useState<College[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [profile, list, cities] = await Promise.all([
          api<Me>("/me"),
          api<College[]>("/colleges"),
          api<Place[]>("/locations"),
        ]);
        if (cancelled) return;
        setMe(profile);
        setColleges(list);
        setPlaces(cities);
        if (profile.profile.registered) return router.replace("/domains");
      } catch (e) {
        if (!cancelled) {
          setLoadError(
            e instanceof ApiError && e.status === 401
              ? "Your session expired. Please sign in again."
              : "We could not load your details. Check your connection and reload.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);

    const form = new FormData(event.currentTarget);
    const collegeName = String(form.get("college") ?? "").trim();
    // If the typed name exactly matches a known college, bind to its id so the
    // analytics group cleanly instead of creating a near-duplicate row.
    const match = colleges.find(
      (c) => c.name.toLowerCase() === collegeName.toLowerCase(),
    );

    try {
      await api("/register", {
        method: "POST",
        json: {
          phone: form.get("phone"),
          college_id: match?.id ?? null,
          college_name: match ? null : collegeName,
          location: form.get("location"),
          // Optional: sent as null rather than "" so the server stores an
          // absent value instead of an empty string that looks like an answer.
          student_id: String(form.get("student_id") ?? "").trim() || null,
        },
      });
      router.replace("/domains");
      return;
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not save your registration. Please try again.",
      );
      setSaving(false);
    }
  }

  if (loadError) {
    return (
      <Shell>
        <p role="alert" className="text-sm text-danger">
          {loadError}
        </p>
        <button
          onClick={() => router.refresh()}
          className="mt-4 rounded-xl border border-line bg-surface-2 px-5 py-2.5 text-sm font-medium"
        >
          Reload
        </button>
      </Shell>
    );
  }

  if (!me) {
    return (
      <Shell>
        <div className="space-y-3" aria-busy="true" aria-label="Loading your details">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-11 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      </Shell>
    );
  }

  const p = me.profile;

  return (
    <Shell>
      <div className="mb-8">
        <p className="mb-2 text-xs text-muted">Step 2 of 4</p>
        <h1 className="text-3xl font-bold tracking-tight text-balance">
          Three quick details and you&rsquo;re in.
        </h1>
        <p className="mt-2 text-sm text-muted">
          Your name and email come from Google and go on your certificate. We ask
          for nothing else we don&rsquo;t need.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-5">
        <Locked label="Name" value={p.name} />
        <Locked label="Email" value={p.email} />

        <Field label="Phone number" name="phone">
          <input
            id="phone"
            name="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            required
            defaultValue={p.phone ?? ""}
            placeholder="98765 43210"
            className={inputClass}
          />
        </Field>

        <Field label="College" name="college" hint="Start typing to find yours, or add a new one.">
          <input
            id="college"
            name="college"
            list="college-options"
            required
            maxLength={160}
            defaultValue={p.college_name ?? ""}
            autoComplete="organization"
            className={inputClass}
          />
          <datalist id="college-options">
            {colleges.map((c) => (
              <option key={c.id} value={c.name} />
            ))}
          </datalist>
        </Field>

        <Field label="Where you're based" name="location" hint="Your city or town.">
          <input
            id="location"
            name="location"
            list="location-options"
            required
            minLength={2}
            maxLength={120}
            defaultValue={p.location ?? ""}
            placeholder="Kochi"
            autoComplete="address-level2"
            className={inputClass}
          />
          <datalist id="location-options">
            {places.map((c) => (
              <option key={c.id} value={c.name} />
            ))}
          </datalist>
        </Field>

        <Field
          label="Student ID"
          name="student_id"
          optional
          hint="Helps your college match you to their records."
        >
          <input
            id="student_id"
            name="student_id"
            maxLength={60}
            defaultValue={p.student_id ?? ""}
            placeholder="CS21001"
            className={inputClass}
          />
        </Field>

        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={saving}
          className="w-full btn px-6 py-4"
        >
          {saving ? "Saving…" : "Continue"}
        </button>
      </form>
    </Shell>
  );
}

const inputClass =
  "w-full rounded-xl border border-line bg-surface-2 px-4 py-3 text-ink placeholder:text-muted/60 focus:border-sky";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <Desk width="max-w-md">
      <Win caption="register.form" bodyClassName="p-6 sm:p-8">
        {children}
      </Win>
    </Desk>
  );
}

function Field({
  label,
  name,
  optional,
  hint,
  children,
}: {
  label: string;
  name: string;
  optional?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={name} className="mb-1.5 flex items-baseline gap-2 text-sm font-medium">
        {label}
        {/* Almost everything here is required, so the exception is what earns a
            label. A field of asterisks tells the student nothing. */}
        {optional && <span className="text-xs font-normal text-muted">optional</span>}
      </label>
      {children}
      {hint && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

/** Identity from Google. Shown so the student can check it, not edit it. */
function Locked({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      <div className="flex items-center justify-between rounded-xl border border-line bg-surface px-4 py-3 text-muted">
        <span className="truncate">{value}</span>
        <span className="ml-3 shrink-0 font-mono text-[10px] tracking-widest text-ok">
          VERIFIED
        </span>
      </div>
    </div>
  );
}
