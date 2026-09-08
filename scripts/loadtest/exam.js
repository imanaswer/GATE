import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";
import { SharedArray } from "k6/data";

// One parse of the token file shared across VUs; parsing per-VU at 10k costs
// more memory than the test itself.
const tokens = new SharedArray("tokens", () =>
  JSON.parse(open(__ENV.TOKENS_FILE || "/tmp/tokens.json")),
);

const BASE = __ENV.BASE_URL || "http://localhost:8099";
const DOMAINS = ["full-stack", "cybersecurity", "data-science", "ai-ml", "cloud-devops"];
// Real pacing: 20 minutes over 15 questions, with reading time. Lower it for a
// smoke run, but a run with THINK=0 measures a workload no student generates —
// it tells you about your own laptop, not about event day.
const THINK = Number(__ENV.THINK_SECONDS ?? 45);

const startTime = new Trend("exam_start_duration", true);
const saveTime = new Trend("autosave_duration", true);
const doubleStarts = new Counter("one_attempt_violations");

export const options = {
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "exam_start_duration": ["p(95)<3000"],
    "autosave_duration": ["p(95)<800"],
    // The constraint holding under concurrency is the point of the exercise.
    "one_attempt_violations": ["count==0"],
    checks: ["rate>0.99"],
  },
};

// VU-local, so each virtual user remembers the attempt it was given. Module
// scope in k6 is per-VU, which is exactly the scope this needs.
let myAttemptId = null;

export default function examJourney() {
  const token = tokens[__VU % tokens.length];
  const auth = { headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } };

  const start = http.post(
    `${BASE}/api/v1/attempts`,
    JSON.stringify({ domain_slug: DOMAINS[__VU % DOMAINS.length] }),
    { ...auth, tags: { name: "start" } },
  );
  startTime.add(start.timings.duration);

  // 409 is correct and expected on any iteration after the first: this student
  // has already attempted. Anything else on a repeat is the one-attempt rule
  // failing under concurrency, which is what we are here to find out.
  const started = start.status === 201 || start.status === 200;
  check(start, { "start accepted or refused as duplicate": (r) => started || r.status === 409 });

  if (!started) {
    sleep(1);
    return;
  }

  const { attempt, questions } = start.json();

  // The assertion the whole run exists to make. Getting the *same* attempt back
  // is the resume path and is correct; a different id means one student now has
  // two attempts and UNIQUE(user_id, event_id) did not hold under concurrency.
  if (myAttemptId !== null && attempt.id !== myAttemptId) {
    doubleStarts.add(1);
  }
  myAttemptId = attempt.id;

  if (!questions || questions.length === 0) return;

  // A real student answers roughly one question per 45s (20 minutes / 15
  // questions, with reading time). Hammering saves back to back measures a
  // workload nobody generates.
  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const option = q.options[Math.floor(Math.random() * q.options.length)];
    const res = http.put(
      `${BASE}/api/v1/attempts/${attempt.id}/answers/${q.position}`,
      JSON.stringify({ option_id: option.id, response_ms: Math.round(40000 + Math.random() * 30000) }),
      { ...auth, tags: { name: "autosave" } },
    );
    saveTime.add(res.timings.duration);
    check(res, { "autosave accepted": (r) => r.status === 200 });
    if (THINK > 0) sleep(THINK * (0.6 + Math.random() * 0.8));
  }

  const submit = http.post(`${BASE}/api/v1/attempts/${attempt.id}/submit`, null, {
    ...auth,
    tags: { name: "submit" },
  });
  check(submit, { "submit scored": (r) => r.status === 200 && r.json().certificate_id });
}
