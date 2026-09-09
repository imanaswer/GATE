import Link from "next/link";

const REASONS: Record<string, string> = {
  no_code: "Google did not send us a sign-in code. This usually means the sign-in was cancelled.",
  exchange_failed: "We could not complete the sign-in. The link may have expired or already been used.",
};

export default async function AuthError({ searchParams }: PageProps<"/auth/error">) {
  const params = await searchParams;
  const reason = typeof params.reason === "string" ? params.reason : "";

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 text-center">
        <p className="mb-3 font-mono text-xs tracking-widest text-danger">SIGN-IN FAILED</p>
        <h1 className="mb-3 text-2xl font-semibold">We could not sign you in</h1>
        <p className="mb-6 text-sm text-muted">
          {REASONS[reason] ?? "Something went wrong during sign-in."}
        </p>
        <Link
          href="/"
          className="btn inline-block px-6 py-3"
        >
          Try again
        </Link>
      </div>
    </main>
  );
}
