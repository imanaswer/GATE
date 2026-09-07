import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  // Only ever redirect to a path on this origin. An open redirect here would let
  // an attacker bounce a freshly-issued session to a domain they control.
  const raw = searchParams.get("next") ?? "/register";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/register";

  if (!code) {
    return NextResponse.redirect(`${origin}/auth/error?reason=no_code`);
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(`${origin}/auth/error?reason=exchange_failed`);
  }

  return NextResponse.redirect(`${origin}${next}`);
}
