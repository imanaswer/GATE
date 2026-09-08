import { ApiError } from "@/lib/api";

/**
 * Admin calls carry a FastAPI-issued HttpOnly cookie, not a Supabase bearer
 * token — a different auth world entirely. `credentials: "same-origin"` is what
 * sends it; there is no token for JavaScript to hold, which is the point.
 */
export async function adminApi<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (json !== undefined) headers.set("Content-Type", "application/json");

  const res = await fetch(`/api/v1/admin${path}`, {
    ...rest,
    headers,
    credentials: "same-origin",
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
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

export type AdminMe = { email: string; name: string; role: "admin" | "viewer" };

export type Overview = {
  students: number;
  registered: number;
  attempts: number;
  in_progress: number;
  submitted: number;
  expired: number;
  certificates: number;
  colleges: number;
  flagged: number;
  average_score: number | null;
  by_domain: { slug: string; name: string; attempts: number; average_score: number | null }[];
  refreshed_at: string;
  stale_seconds: number;
};

export type AdminStudent = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  student_id: string | null;
  college_name: string | null;
  course: string | null;
  academic_year: number | null;
  registered: boolean;
  attempt_status: "in_progress" | "submitted" | "expired" | null;
  domain_name: string | null;
  score: number | null;
  certificate_id: string | null;
  submitted_at: string | null;
};

export type StudentDetail = AdminStudent & {
  attempt_id: string | null;
  correct: number | null;
  wrong: number | null;
  skipped: number | null;
  questions: {
    position: number;
    topic: string;
    difficulty: string;
    is_correct: boolean | null;
    skipped: boolean;
    response_ms: number | null;
  }[];
  flags: { type: string; detail: Record<string, unknown>; occurred_at: string }[];
};

export type AdminQuestion = {
  id: string;
  body: string;
  code: string | null;
  topic: string;
  difficulty: "easy" | "medium" | "hard";
  type: string;
  status: "draft" | "active" | "retired";
  explanation: string | null;
  domain_slug: string;
  domain_name: string;
  options: { id: string; body: string; is_correct: boolean }[];
};

export type QuestionStat = {
  id: string;
  body: string;
  topic: string;
  difficulty: string;
  status: string;
  domain_slug: string;
  seen: number;
  answered: number;
  correct: number;
  skipped: number;
  correct_rate: number | null;
  avg_ms: number | null;
};

export type CollegeStat = {
  id: string;
  name: string;
  city: string | null;
  students: number;
  completed: number;
  average_score: number | null;
  top_score: number | null;
};

export type IntegrityFlag = {
  type: string;
  detail: Record<string, unknown>;
  occurred_at: string;
  user_id: string;
  name: string;
  email: string;
  college_name: string | null;
  score: number | null;
};
