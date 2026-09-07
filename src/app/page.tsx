import { redirect } from "next/navigation";
import { GoogleSignIn } from "@/components/GoogleSignIn";
import { createClient } from "@/lib/supabase/server";

export default async function Landing({ searchParams }: PageProps<"/">) {
  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : "/register";

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) redirect(next.startsWith("/") ? next : "/register");

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="rise w-full max-w-md">
        <div className="mb-10 text-center">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 font-mono text-xs tracking-widest text-accent">
            ⚡ TECH ARENA 2026
          </p>
          <h1 className="text-balance text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
            15 challenges.
            <br />
            20 minutes.
          </h1>
          <p className="mx-auto mt-4 max-w-sm text-balance text-muted">
            Pick your domain, take on the arena, and walk away with a verified
            certificate.
          </p>
        </div>

        <div className="rounded-2xl border border-line bg-surface p-6">
          <ol className="mb-6 space-y-3 text-sm">
            {[
              "Sign in with Google",
              "Complete your registration",
              "Choose your challenge domain",
              "15 challenges, one attempt",
            ].map((step, i) => (
              <li key={step} className="flex items-center gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md border border-line bg-surface-2 font-mono text-xs text-accent">
                  {i + 1}
                </span>
                <span className="text-muted">{step}</span>
              </li>
            ))}
          </ol>
          <GoogleSignIn next={next} />
        </div>
      </div>
    </main>
  );
}
