import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const PROTECTED = ["/register", "/arena"];

function isProtected(path: string) {
  return PROTECTED.some((p) => path.startsWith(p));
}

function toSignIn(request: NextRequest, path: string) {
  const url = request.nextUrl.clone();
  url.pathname = "/";
  url.searchParams.set("next", path);
  return NextResponse.redirect(url);
}

/**
 * Refreshes the Supabase session on every request. Without this the access token
 * expires mid-exam and autosaves start failing silently — which is the single
 * worst failure this platform can have.
 *
 * Runs on every non-API route, so it is also the one place that can take the
 * whole site down. It must not: a missing environment variable or a Supabase
 * outage should never stop `/verify/{id}` resolving for an employer holding a
 * printed certificate, or the landing page from explaining what went wrong.
 * Both are handled as "no session" — which redirects the two protected routes
 * to sign-in and leaves everything else working. Fail safe, not fail open.
 */
export async function updateSession(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    // Deliberately loud: this is a deployment that will never be able to sign
    // anyone in, and the reason belongs in the logs rather than in a 500.
    console.error(
      "[auth] NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not " +
        "set. Sign-in is disabled; public pages still render.",
    );
    return isProtected(path) ? toSignIn(request, path) : NextResponse.next({ request });
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl, supabaseKey, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (list) => {
        list.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        list.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });

  let user = null;
  try {
    ({
      data: { user },
    } = await supabase.auth.getUser());
  } catch (error) {
    // Supabase unreachable. Treat as signed out rather than 500-ing every page.
    console.error("[auth] could not verify the session:", error);
  }

  if (!user && isProtected(path)) return toSignIn(request, path);

  return response;
}
