"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { adminApi } from "@/lib/adminApi";
import { ApiError } from "@/lib/api";

export default function AdminLogin() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(form: FormData) {
    setBusy(true);
    setError(null);
    try {
      await adminApi("/login", {
        method: "POST",
        json: { email: form.get("email"), password: form.get("password") },
      });
      router.replace("/admin");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not sign in.");
      setBusy(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <form action={submit} className="w-full max-w-sm">
        <h1 className="text-2xl font-bold tracking-tight">Admin sign-in</h1>
        <p className="mt-1 text-sm text-muted">
          Accounts are created from the shell with <code>pnpm admin:create</code>.
        </p>

        <label className="mt-6 block text-sm">
          Email
          <input
            name="email"
            type="email"
            required
            autoComplete="username"
            className="mt-1 w-full rounded-xl border border-line bg-surface px-3 py-2"
          />
        </label>
        <label className="mt-4 block text-sm">
          Password
          <input
            name="password"
            type="password"
            required
            autoComplete="current-password"
            className="mt-1 w-full rounded-xl border border-line bg-surface px-3 py-2"
          />
        </label>

        {error && (
          <p role="alert" className="mt-4 text-sm text-danger">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="btn mt-6 w-full px-4 py-2.5"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
