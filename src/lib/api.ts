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
  init: RequestInit & { json?: unknown; sessionToken?: string } = {},
): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const { json, sessionToken, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (session) headers.set("Authorization", `Bearer ${session.access_token}`);
  if (json !== undefined) headers.set("Content-Type", "application/json");
  // Lets the server notice a second device and log it. It never blocks the
  // request — a student whose phone dies must be able to continue on a laptop.
  if (sessionToken) headers.set("X-Session-Token", sessionToken);

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

export type Option = { id: string; body: string };

export type Question = {
  position: number;
  type: "mcq" | "code_output" | "debug" | "scenario" | "logic";
  body: string;
  code: string | null;
  language: string | null;
  topic: string;
  difficulty: "easy" | "medium" | "hard";
  options: Option[];
  selected_option_id: string | null;
};

export type Attempt = {
  id: string;
  status: "in_progress" | "submitted" | "expired";
  domain_slug: string;
  domain_name: string;
  started_at: string;
  expires_at: string;
  remaining_seconds: number;
  session_token: string;
};

export type Paper = {
  attempt: Attempt | null;
  questions: Question[];
  finished?: boolean;
};

export type Result = {
  attempt_id: string;
  status: "submitted" | "expired";
  domain_name: string;
  domain_slug: string;
  score: number;
  total: number;
  correct: number;
  wrong: number;
  skipped: number;
  duration_seconds: number | null;
  submitted_at: string | null;
};

export type Domain = {
  id: string;
  slug: string;
  name: string;
  icon: string | null;
  description: string | null;
};
