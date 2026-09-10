"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { adminApi, type AdminMe } from "@/lib/adminApi";

const TABS = [
  ["/admin", "Overview"],
  ["/admin/students", "Students"],
  ["/admin/questions", "Questions"],
  ["/admin/analytics", "Analytics"],
] as const;

/**
 * The gate is here rather than in `session.ts`: the admin session is a cookie
 * FastAPI issued and only FastAPI can verify, and checking it in middleware
 * would mean putting ADMIN_SECRET into the Next runtime as well. This layout
 * just asks the API who it is and gets out of the way — a 401 redirects.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<AdminMe | null>(null);
  const isLogin = pathname === "/admin/login";

  useEffect(() => {
    if (isLogin) return;
    adminApi<AdminMe>("/me")
      .then(setMe)
      .catch(() => router.replace("/admin/login"));
  }, [isLogin, pathname, router]);

  if (isLogin) return <>{children}</>;
  if (!me) {
    return (
      <main className="flex flex-1 justify-center px-6 py-16">
        <div className="h-40 w-full max-w-5xl animate-pulse rounded-2xl bg-surface-2" aria-busy="true" />
      </main>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      {/* Real navigation, so it keeps its own tabs — it just wears the menu
          bar's chrome so the panel reads as part of the same desk. */}
      <header className="sticky top-0 z-30 border-b border-line/70 bg-surface/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-2.5">
          <span aria-hidden="true" className="flex shrink-0 items-center gap-1.5">
            <span className="size-2.5 rounded-full bg-[#ff5f57]" />
            <span className="size-2.5 rounded-full bg-[#febc2e]" />
            <span className="size-2.5 rounded-full bg-[#28c840]" />
          </span>
          <span className="font-mono text-xs tracking-widest text-accent-soft">TECH ARENA ADMIN</span>
          <nav className="flex gap-4 text-sm">
            {TABS.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                aria-current={pathname === href ? "page" : undefined}
                className={
                  pathname === href
                    ? "font-semibold text-fg underline underline-offset-4"
                    : "text-muted hover:text-fg"
                }
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted">
            <span>
              {me.email}
              {me.role === "viewer" && " · read-only"}
            </span>
            <button
              onClick={async () => {
                await adminApi("/logout", { method: "POST" });
                router.replace("/admin/login");
              }}
              className="rounded-lg border border-line px-2 py-1 hover:text-fg"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
