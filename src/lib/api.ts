import { createClient } from "@/lib/supabase/client";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Calls the FastAPI backend with the current Supabase access token.
 * Same origin (rewritten to the Python function), so no CORS and no token in a
 * query string where it would land in access logs.
 */
export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const { json, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (session) headers.set("Authorization", `Bearer ${session.access_token}`);
  if (json !== undefined) headers.set("Content-Type", "application/json");

  const res = await fetch(`/api/v1${path}`, {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      // FastAPI validation errors arrive as a list of issues; show the first.
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail[0].msg.replace(/^Value error, /, "");
      }
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(res.status, detail);
  }

  return res.status === 204 ? (undefined as T) : res.json();
}

export type Profile = {
  id: string;
  email: string;
  name: string;
  phone: string | null;
  college_id: string | null;
  college_name: string | null;
  course: string | null;
  academic_year: number | null;
  student_id: string | null;
  registered: boolean;
};

export type AttemptSummary = {
  id: string;
  status: "in_progress" | "submitted" | "expired";
  domain_slug: string;
  domain_name: string;
  score: number | null;
};

export type Me = { profile: Profile; attempt: AttemptSummary | null };
export type College = { id: string; name: string; city: string | null };
