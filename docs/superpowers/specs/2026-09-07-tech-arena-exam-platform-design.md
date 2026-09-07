# Tech Arena — Exam Platform Design

Date: 2026-09-07
Status: awaiting approval

## 0. Decisions taken (from you)

| Question | Decision |
|---|---|
| Question bank | Seed now (LLM-drafted, ~200/domain), CSV/XLSX import so curated questions replace the seed before the event |
| Event shape | **Scheduled slots** — colleges book a window; a few thousand start per slot |
| Stack | Next.js + FastAPI + Postgres, on **Vercel + Supabase** |
| Certificates | **Participation** — every student who submits gets one |

---

## 1. Where your spec is wrong, and what I'm doing instead

Six changes. Each is a real risk in the spec as written, not a preference.

### 1.1 `UNIQUE(college_id, student_id)` must NOT be a hard block

Your spec: "consider college + student ID uniqueness to reduce duplicate participation."

Register numbers get mistyped. If student A typos and lands on student B's register number, B is permanently locked out of the event with no self-service fix, and your organizer gets a support queue on event day. Worse, colleges reuse ID formats, so cross-college collisions are real.

**Instead:** `UNIQUE(user_id, event_id)` is the hard constraint — one Google account, one attempt, enforced by the database. `(college_id, student_id)` gets a **partial unique index that only warns**: on collision we still register the student, write a `suspicious_activity` row of type `duplicate_student_id`, and surface it in the admin dashboard for review. Fairness beats tidiness; a human resolves it.

### 1.2 Browser anti-cheating prevents almost nothing — say so out loud

What tab-switch and fullscreen-exit detection actually catches: a student who alt-tabs on the same device, in the same browser, with the page focused. That is it.

What it cannot detect, at all, ever:
- A second device (phone, laptop) with ChatGPT open next to the exam
- A screen shared over Discord/Meet to a friend answering for them
- Someone else sitting next to them
- A browser extension or a second browser profile
- Screenshots

Any vendor claiming otherwise is selling you something. Your instinct to **flag, not disqualify** is exactly right and I'm keeping it. The signals that actually carry information are not the tab switches — they're **per-question response times** (a 12-second correct answer on a hard debugging question is more suspicious than 30 tab switches) and **duplicate answer-sequence patterns across students in the same slot**. Both are computed server-side, post-hoc, and both go on the flag list.

The real anti-cheat measures here are structural, and they're already in the design: a large randomized bank, randomized option order, a short server-authoritative timer, and no correct answers ever reaching the client. Proctoring is a separate product; we are not building it, and I won't pretend the tab counter substitutes for it.

### 1.3 Certificate generation must be lazy, not eager

Your spec: exam completed → generate certificate → store PDF.

At 50,000 students that's 50,000 PDF renders you must provision workers for, and most students never download theirs. Eager generation buys you a worker fleet, a queue, and a new failure mode on the busiest day.

**Instead:** on submit we synchronously create the `certificates` row — certificate ID, issue date, verification hash. That is the certificate; it's immediately valid, immediately verifiable at `/verify/{id}`, and the student sees "✓ Certificate generated" instantly with zero PDF work. The **PDF renders on first download** and is then cached in Supabase Storage. Admin batch exports and a nightly cron can pre-warm PDFs if you want them ready. Same student experience, none of the fleet.

### 1.4 Batch PDF for a filtered set of 50,000 students is not a feature, it's an outage

Your spec asks for "filtered batch PDF ... where practical." It isn't practical at that size and nobody reads a 50,000-page PDF.

**Instead:** batch PDF is capped at **500 students** and runs as a background job that emails/links a ZIP when done. Above 500 the UI directs you to CSV, which is what you actually want for that many rows anyway. CSV export streams row-by-row out of a server-side cursor — it never materializes in memory, so a 50k-row export is a constant-memory operation.

### 1.5 Exam duration: 20 minutes, not 15

15 questions in 15 minutes is 60 seconds each. Your own spec asks for code-output, debugging, and scenario questions — a debugging question cannot be read, understood, and answered in 60 seconds. A timer that punishes reading speed measures reading speed.

**20 minutes** (80s/question). Configurable per event, so you can tune it after the pilot.

### 1.6 Multiple-session detection must not kill the attempt

A student's phone dies and they switch to a laptop. That is not cheating, and terminating their attempt over it is the single most damaging bug this platform could ship.

**Instead:** each attempt carries a `session_token`. A request from a different session is **allowed** — it takes over as the active session, and we log a `session_takeover` suspicious-activity row with both device fingerprints. Two sessions ping-ponging rapidly is a strong signal and gets flagged. Nobody gets locked out mid-exam by our heuristic.

---

## 2. Architecture

```
Browser
  └─ Next.js 15 (App Router, TS, Tailwind) ── Vercel
       └─ /api/v1/*  ──rewrite──▶  FastAPI (Python 3.13, Vercel Fluid Compute)
                                     ├── Supabase Postgres (via transaction pooler)
                                     ├── Upstash Redis (rate limits, locks, hot config)
                                     └── Supabase Storage (certificate PDFs)
  └─ Supabase Auth (Google OAuth) ── issues JWT, verified by FastAPI via JWKS
```

**One Vercel project, one repo, one deploy.** FastAPI is mounted as a single ASGI Python function; `/api/v1/(.*)` rewrites to it. Same origin means no CORS and cookies that just work — this is worth more than the tidiness of a separate API service.

### Deviations from your spec, with reasons

| Your spec | Built | Why |
|---|---|---|
| Redis | **Upstash Redis** | Supabase has no Redis. Upstash is HTTP-based, so it works from serverless with no connection pool. |
| AWS / S3 | **Vercel + Supabase Storage** | Supabase Storage is S3-compatible. Nobody has to own an AWS account at 9am on event day. |
| Google OAuth wired by hand | **Supabase Auth Google provider** | It's the same OAuth, already implemented, with session refresh handled. We verify its JWT server-side; we do not trust it blindly. |
| Eager certificate PDFs | **Lazy render, cached** | §1.3 |
| Celery/worker fleet | **Vercel Cron + a `jobs` table** | At scheduled-slot volume there is no job load that justifies a worker fleet. Revisit if batch exports become hot. |

### Scale sizing (scheduled slots)

Slot capacity **5,000 students**. That gives:
- Exam starts: 5,000 over ~5 min ≈ **17/s** peak
- Autosaves: 5,000 concurrent × 1 write/~45s ≈ **110 writes/s** steady
- Reads: served from the attempt row, already in Postgres page cache

This is an ordinary Postgres workload. The failure modes that actually matter at this shape are **not** CPU:
1. **Connection exhaustion.** Serverless functions × connections = the classic blowup. Mitigation: Supabase **transaction-mode pooler** exclusively, `SQLAlchemy` with `NullPool` (the pooler is the pool).
2. **Exam-start contention.** `UNIQUE(user_id, event_id)` serializes concurrent starts for the same user, which is correct and cheap — but the start transaction must be short. It does: insert attempt, select 15 question IDs, insert `attempt_questions`. No PDF, no email, no analytics.
3. **Admin dashboard scans.** A dashboard doing `COUNT(*)` over 50k rows on every page load will be the slowest thing in the system. Overview counters are **materialized and refreshed on a 60s cron**, not computed live.

Load test targets (k6): 1k → 5k → 10k concurrent, against the exam-start and autosave paths specifically. Anything above 10k only matters if you move to gun-start.

---

## 3. Database schema

```sql
-- identity
colleges        (id, name, city, state, created_at)  UNIQUE(lower(name))
users           (id=auth.uid, email UNIQUE, name, phone, college_id FK,
                 course, academic_year, student_id, created_at)
admin_users     (id, email UNIQUE, role[admin|viewer], password_hash, created_at)

-- content
domains         (id, slug UNIQUE, name, icon, description, is_active)
questions       (id, domain_id FK, type[mcq|code_output|debug|scenario|logic],
                 body, code_snippet, topic, difficulty[easy|medium|hard],
                 explanation, status[draft|active|retired], version,
                 created_by, created_at)
question_options(id, question_id FK ON DELETE CASCADE, body, is_correct, position)

-- event + attempts
exam_events     (id, name, slug UNIQUE, duration_seconds DEFAULT 1200,
                 opens_at, closes_at, blueprint jsonb, is_active)
exam_attempts   (id, user_id FK, event_id FK, domain_id FK,
                 status[in_progress|submitted|expired],
                 started_at, expires_at, submitted_at,
                 score, correct_count, wrong_count, skipped_count,
                 session_token, ip, user_agent,
                 UNIQUE(user_id, event_id))            -- the one-attempt rule
attempt_questions(id, attempt_id FK ON DELETE CASCADE, question_id FK,
                 position, option_order int[],          -- per-attempt shuffle
                 UNIQUE(attempt_id, position),
                 UNIQUE(attempt_id, question_id))       -- no dupes in an attempt
answers         (id, attempt_id FK ON DELETE CASCADE, attempt_question_id FK,
                 selected_option_id FK NULL,            -- NULL = skipped
                 is_correct,                            -- server-computed
                 response_ms, answered_at,
                 UNIQUE(attempt_question_id))           -- upsert target

-- output + safety
certificates    (id, attempt_id FK UNIQUE, certificate_id TEXT UNIQUE,
                 verify_hash, issued_at, pdf_path NULL, pdf_generated_at NULL)
suspicious_activity(id, attempt_id FK, type, detail jsonb, occurred_at)
jobs            (id, kind, params jsonb, status, result_path, created_at, finished_at)
```

**Indexes that matter:** `answers(attempt_id)`, `attempt_questions(attempt_id, position)`,
`exam_attempts(event_id, status)`, `exam_attempts(domain_id, status)`,
`users(college_id)`, `questions(domain_id, difficulty, status)`,
partial `UNIQUE(college_id, student_id) WHERE student_id IS NOT NULL` — **advisory only**, checked in app code to emit a flag rather than reject.

**Correct answers live only in `question_options.is_correct`.** No API response ever serialises that column. The exam endpoint selects `id, body` and nothing else.

---

## 4. Exam engine

### Selection (not random)

Blueprint stored per event as JSON, default `{easy: 5, medium: 7, hard: 3}`.

Per difficulty tier, select from the domain's `active` questions with a **topic-spread pass**: shuffle topics, take round-robin across topics until the tier quota is filled, then shuffle the result. Two students in the same slot get different questions *and* different topic mixes; nobody gets five questions on the same topic.

Option order is shuffled once at attempt creation and stored in `attempt_questions.option_order`, so a refresh shows the same order — a shuffle-on-every-render is disorienting and looks like a bug.

**Guard:** exam-start fails loudly with a clear admin-facing error if a domain lacks enough active questions for its tier quotas. Silent degradation here means an unfair exam.

### Timer

`started_at` and `expires_at` written at attempt creation, server-side, from the DB clock. The client timer is decoration. Every answer-save and the submit endpoint check `now() < expires_at + 30s grace` — the grace absorbs network lag on a final answer, and 30s of grace cannot be gamed into a meaningful advantage.

A cron sweeps `in_progress` attempts past `expires_at` and auto-submits them, so a student who closes their laptop still gets scored and certificated.

### Autosave and resume

`PUT /attempts/{id}/answers/{position}` upserts on `UNIQUE(attempt_question_id)` and returns the saved state. Idempotent by construction — retry it as many times as you like. The UI shows a per-question saved/saving/failed indicator and retries with backoff; a failed save is never silent.

Resume: `GET /attempts/current` returns the live attempt with all saved answers and remaining seconds. Refresh, crash, and network drop all land in the same place. **A second attempt is never created** — the unique constraint makes that structurally impossible, not merely unlikely.

### Submit

Idempotent via an `Idempotency-Key` header and a Redis lock on `attempt:{id}:submit`. Scoring runs server-side inside one transaction: grade every answer, write counts, create the certificate row, mark submitted. A repeat submit returns the same result, not an error.

---

## 5. Student journey

QR/link → landing → Google login → registration (name and email prefilled and **read-only** from Google; phone, college, course, year, student ID collected) → domain select → mission briefing (rules, timer, what's flagged, explicitly stated) → exam → submit → **MISSION COMPLETE** with score and certificate → certificate view/download.

No ranking. No tech profile. No leaderboard. Per your spec, and I agree — a public ranking at a college event produces exactly one good feeling and several thousand bad ones.

Exam UI: `⚡ CHALLENGE 04 / 15`, level bands (Foundation 1–5, Problem Solver 6–10, Final 11–15), progress bar, difficulty chip, saved-state indicator, timer that turns amber at 5 min and red at 1 min. Animations are CSS transforms and opacity only — nothing that touches layout, nothing that runs during scroll. Full keyboard navigation, visible focus rings, `prefers-reduced-motion` respected, WCAG AA contrast.

---

## 6. API surface

```
POST   /api/v1/auth/session          exchange Supabase JWT → app session
POST   /api/v1/register              create/complete profile
GET    /api/v1/me
GET    /api/v1/domains
POST   /api/v1/attempts              start (idempotent; 409 if already attempted)
GET    /api/v1/attempts/current      resume
PUT    /api/v1/attempts/{id}/answers/{position}
POST   /api/v1/attempts/{id}/submit  (Idempotency-Key)
GET    /api/v1/attempts/{id}/result
POST   /api/v1/attempts/{id}/events  tab switch / fullscreen exit / disconnect
GET    /api/v1/certificates/{cert_id}         metadata
GET    /api/v1/certificates/{cert_id}/pdf     lazy render + cache
GET    /api/v1/verify/{cert_id}               public, minimal fields, rate-limited

-- admin (separate auth, separate rate limits)
POST   /api/v1/admin/login
GET    /api/v1/admin/overview                 materialized counters
GET    /api/v1/admin/students                 search/filter/paginate (keyset)
GET    /api/v1/admin/students/{id}
GET    /api/v1/admin/questions                CRUD + bulk import/export
GET    /api/v1/admin/analytics/questions
GET    /api/v1/admin/analytics/colleges
POST   /api/v1/admin/export/csv               streaming
POST   /api/v1/admin/export/pdf               job; ≤500 students
```

Rate limits (Upstash, sliding window): register 5/min/user, answer-save 60/min/attempt, submit 3/min/attempt, verify 30/min/IP, admin export 5/hour/admin. Pagination is **keyset, not OFFSET** — `OFFSET 40000` on the student list is a table scan.

---

## 7. Certificate verification

`/verify/{certificate_id}` is public and shows the **minimum**: valid badge, name, college, domain, certificate ID, issue date. No score, no email, no phone. QR encodes that URL. Rate-limited and non-enumerable — certificate IDs are random (`TA-2026-<10 base32 chars>`), not sequential, so the endpoint can't be walked to harvest the student roster.

---

## 8. Build order

**Phase 1 — Foundation.** Repo, Next.js + FastAPI on Vercel, Supabase schema + migrations, Supabase Auth Google, registration, one-attempt constraint. *Ends with: a student can log in and register, twice, and the second time is refused by the database.*

**Phase 2 — Question bank.** Schema, CSV/XLSX import with validation, admin CRUD, and a seeded bank of ~200 questions × 5 domains so the system is testable end-to-end. *Ends with: a real bank you can replace.*

**Phase 3 — Exam engine.** Blueprint selection, server timer, autosave, resume, idempotent submit, backend scoring. **This is the part that cannot be degraded on event day.** *Ends with: a full exam taken, refreshed mid-way, resumed, and scored correctly.*

**Phase 4 — Student UI.** Landing, domain select, briefing, exam arena, completion screen.

**Phase 5 — Certificates.** Row on submit, lazy PDF, QR, `/verify/{id}`.

**Phase 6 — Admin.** Auth, overview, student list + detail, question management, question/college analytics, CSV stream, capped batch PDF.

**Phase 7 — Hardening.** Rate limits, suspicious-activity signals, Sentry, k6 load tests at 1k/5k/10k, seed-data soak.

Phases 1–3 are the MVP. 5 matters to you. 6 is mostly post-event work and a bare student list covers event day if we run out of time.

## 9. Explicitly not building

Public leaderboards, tech profiles, career pages, gamified XP, proctoring/webcam, live invigilation, student-to-student anything, mobile apps, i18n. Each is either counterproductive (§5) or a separate product (proctoring).

## 10. Open risk — needs your action this week

**Google OAuth verification is an external dependency with lead time and it can sink the event.** An unverified OAuth app is capped at 100 users, the cap counts over the project's lifetime, and it cannot be reset. Verification takes days to weeks.

Action now, before any of this matters: in Google Cloud Console → OAuth consent screen, confirm the publishing status, request **only** non-sensitive scopes (`openid`, `email`, `profile` — nothing touching Gmail/Drive/Calendar, which triggers the slow review path), and start verification today. Supabase Auth uses your own Google client, so this is your project's cap, not Supabase's.

If verification won't land in time, the fallback is Supabase email OTP as a second login method — same one-attempt enforcement, no Google dependency. Cheap to add; say the word and I'll build it alongside.
