"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

export function GoogleSignIn({ next = "/register" }: { next?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn() {
    setBusy(true);
    setError(null);
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    });
    if (error) {
      setError("Could not reach Google. Check your connection and try again.");
      setBusy(false);
    }
    // On success the browser navigates away; leave the button disabled.
  }

  return (
    <div className="w-full">
      <button
        onClick={signIn}
        disabled={busy}
        className="group flex w-full items-center justify-center gap-3 rounded-xl bg-accent px-6 py-4 font-semibold text-accent-ink transition-transform duration-150 hover:-translate-y-0.5 active:translate-y-0 disabled:cursor-wait disabled:opacity-60 disabled:hover:translate-y-0"
      >
        <GoogleMark />
        {busy ? "Connecting to Google…" : "Continue with Google"}
      </button>
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
      <p className="mt-3 text-center text-xs text-muted">
        One Google account, one attempt.
      </p>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M23 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.2a5.3 5.3 0 0 1-2.3 3.5v2.9h3.7c2.2-2 3.4-5 3.4-8.6Z" />
      <path fill="#34A853" d="M12 24c3.1 0 5.7-1 7.6-2.8l-3.7-2.9c-1 .7-2.3 1.1-3.9 1.1-3 0-5.5-2-6.4-4.7H1.8v3C3.7 21.4 7.6 24 12 24Z" />
      <path fill="#FBBC05" d="M5.6 14.7a7.2 7.2 0 0 1 0-4.6v-3H1.8a12 12 0 0 0 0 10.6l3.8-3Z" />
      <path fill="#EA4335" d="M12 4.8c1.7 0 3.2.6 4.4 1.7l3.3-3.3C17.7 1.2 15.1 0 12 0 7.6 0 3.7 2.6 1.8 6.1l3.8 3c.9-2.7 3.4-4.3 6.4-4.3Z" />
    </svg>
  );
}
