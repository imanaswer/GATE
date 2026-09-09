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
    <main className="flex flex-1 flex-col justify-center px-6 py-16 sm:px-10">
      <div className="rise w-full max-w-lg">
        <p className="mb-6 text-sm text-accent">Tech Arena 2026</p>

        {/* The two numbers are the whole offer, so they get display size rather
            than being buried in a sentence about them. */}
        <h1 className="text-5xl leading-[0.95] font-bold tracking-tight text-balance sm:text-6xl">
          <span className="tally block">15 challenges.</span>
          <span className="tally block text-accent">20 minutes.</span>
        </h1>

        <p className="mt-6 max-w-md text-lg leading-relaxed text-balance text-muted">
          Pick the domain you know best and take it on. Everyone who finishes
          leaves with a certificate anyone can verify.
        </p>

        <div className="mt-10 max-w-sm">
          <GoogleSignIn next={next} />
          <p className="mt-4 text-sm text-muted">
            One attempt per person. Takes about a minute to set up.
          </p>
        </div>

        <dl className="mt-14 grid grid-cols-3 gap-6 border-t border-line pt-6 text-sm">
          {[
            ["5", "domains"],
            ["15", "challenges"],
            ["20", "minutes"],
          ].map(([value, label]) => (
            <div key={label}>
              <dt className="sr-only">{label}</dt>
              <dd>
                <span className="tally block text-2xl font-bold">{value}</span>
                <span className="text-muted">{label}</span>
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </main>
  );
}
