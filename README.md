# Tech Arena

A technical aptitude exam platform. Design and rationale live in
[`docs/superpowers/specs/2026-09-07-tech-arena-exam-platform-design.md`](docs/superpowers/specs/2026-09-07-tech-arena-exam-platform-design.md).

```
Next.js 16 (App Router, TS, Tailwind 4)   ── Vercel
  └─ /api/v1/*  ──rewrite──▶  FastAPI (Python) ── Supabase Postgres
  └─ Supabase Auth (Google OAuth)
```

Same origin for the API, so there is no CORS layer and no token in a query
string. `vercel.json` owns that rewrite.

## Status

**All seven phases complete** — auth, registration, the one-attempt constraint, the
question bank, the exam engine (blueprint selection, server-authoritative
timer, autosave, resume, idempotent submit, backend scoring), the student UI end
to end, participation certificates, the admin panel, and hardening.

The arena is the screen that matters most and it sits behind Google sign-in, so
`/preview` renders it with fixture data — every question type, save state and
timer threshold, no API calls. It 404s in production.

⚠️ **The seed bank is LLM-authored and has not been reviewed by a subject
expert.** `bank:check` verifies quantity and distribution, not correctness.
Have SMEs review it before the event and replace it with `pnpm bank:import` —
that path is exactly what the seed exists to exercise.

## Setup

```bash
pnpm install
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env.local     # then fill it in
```

**Supabase**

1. Create a project. Copy the URL and anon key into `.env.local`. Leave
   `ALLOW_HS256_JWT` unset — new projects sign with asymmetric JWKS keys, and
   the symmetric path is refused outright when `VERCEL_ENV=production`.
2. `DATABASE_URL` must be the **transaction pooler** URI (port 6543), not the
   direct 5432 one — serverless instances against a direct port exhaust
   Postgres connections.
3. Apply the schema: `pnpm db:push` (uses `MIGRATION_DATABASE_URL`, the
   direct 5432 connection — transaction-mode pooling does not reliably run DDL)
4. Authentication → Sign In / Providers → **Google**: paste your Google OAuth
   client ID and secret, and add the callback Supabase shows you to the Google
   client's authorised redirect URIs.
5. Authentication → URL Configuration → add `https://<your-domain>/auth/callback`
   and `http://localhost:3000/auth/callback` to the redirect allow-list.

**Set `SITE_URL` in production** (e.g. `https://arena.example.com`). It is the
origin printed into every certificate QR code. Without it the URL is rebuilt
from the forwarded headers, which is right in most cases but would let a preview
deployment stamp its own throwaway domain onto a certificate that outlives it.

**Google OAuth — start this first, it has lead time.** An unverified OAuth app
is capped at 100 users for the lifetime of the project and the cap cannot be
reset. Request only `openid`, `email`, and `profile`; anything touching Gmail or
Drive puts you in the slow review queue. See spec §10.

## Running

```bash
pnpm dev          # Next.js only — /api/v1/* will 404
pnpm dev:full     # vercel dev: Next.js + the Python function + the rewrite
```

Use `pnpm dev:full` for anything that touches the API.

Two local-only gotchas, both already handled in this repo:

- `vercel dev` reads `.env.local` for Next.js but only passes **`.env`** to the
  Python function. Keep both; `.env` is what the API sees locally.
- The Vercel Python runtime needs **3.12+**. `.python-version` pins 3.13 for
  both the deploy and your local `uv`/pyenv.

## Certificates

Every finalised attempt gets one — submitted, timed out, or swept by cron alike,
because all three route through `exam.score()`.

What the row is: `TA-<year>-<10 chars>`, drawn from an alphabet with no `I`, `L`,
`O`, `U`, `0` or `1` so it survives being read off a printed page. Creating that
row *is* issuing the certificate; it is valid and verifiable the moment it
exists. Re-submitting never mints a second one.

The PDF is drawn on demand at `/api/v1/certificates/{id}/pdf`, not eagerly on
submit — most students never download theirs, and provisioning a render fleet
for the ones who don't is how event day breaks. It is **not cached**: the
`pdf_path` / `pdf_generated_at` columns stay NULL. A render is ~20ms of CPU;
cache it to Supabase Storage if download volume ever shows up in the numbers.

`/verify/{id}` is public — no account, because an employer holding a printout
has none. It shows the minimum: valid badge, name, college, domain, ID, issue
date, check code. **No score, no email, no phone.** Certificate IDs are random,
not sequential, so the endpoint cannot be walked to harvest the roster, and an
unknown ID and a malformed one return the same 404. Rate limiting is Phase 7.

## Admin

There is no self-service signup and there should not be. The first account is
created from a shell that already has database access:

```bash
pnpm admin:create you@example.com --role admin   # or --role viewer
pnpm admin:list
```

`ADMIN_SECRET` must be set or the panel refuses to issue a session — never
falls back to a default anyone could forge. Admins sign in at `/admin` against
`admin_users`, not Google: an admin account must not depend on an OAuth app
whose verification status is itself a project risk (spec §10). The session is an
HttpOnly, SameSite=Lax cookie issued by FastAPI, so no token is readable from
JavaScript and enforcement stays in one place — the Next middleware deliberately
does **not** gate `/admin`, because that would mean putting `ADMIN_SECRET` into
the Next runtime too.

`admin` can write, `viewer` can only read. Questions are **retired, never
deleted** — deleting one would cascade away the `attempt_questions` rows that
explain the score of every student who was given it.

Overview counters come from a one-row `admin_overview` table refreshed by a
one-minute cron, not counted live: `COUNT(*)` over every attempt on each
dashboard load would be the slowest thing in the system. The screen says how
stale they are rather than pretending to be live.

CSV export streams in constant memory via batched keyset pagination — not a
server-side named cursor, which would hold a connection open for the whole
stream and, with a pool of 2, starve the exam path on event day.

Batch certificate PDFs come back as a **ZIP streamed directly from the request**,
capped at 500. The spec called for a background job on the assumption that
rendering is expensive; it is ~20ms, so 500 is ten seconds inside a 300s
timeout. The `jobs` table stays unused, and that is the point. The cap is about
nobody reading a 50,000-certificate archive, not about cost — above it, CSV is
what you actually wanted.

## Hardening

### What is rate limited, and what deliberately is not

Limits live in Postgres, not Upstash. Every limited endpoint here is low-volume,
and on the one that isn't authenticated the limiter is *cheaper than the thing it
protects* — a single-row upsert against the five-table join behind `/verify` — so
it lowers total database work under abuse rather than amplifying it. Old windows
are swept by the attempt-expiry cron, so it needs no schedule of its own.

| Path | Limit | Keyed on |
|---|---|---|
| `GET /certificates/{id}` | 30 / min | IP |
| `GET /certificates/{id}/pdf` | 10 / min | IP |
| `POST /register` | 5 / min | user — *not* IP, because a whole college shares one NAT address |
| `POST /admin/login` | 5 failures / 5 min per email, 10 per IP | both, since either alone is evadable |
| `GET /admin/export/pdf` | 5 / hour | admin |

Two paths are **deliberately unlimited**, and both are deliberate against the
spec:

- **Answer autosave.** The hot path — about 110 writes a second at slot
  capacity. A save is an idempotent upsert onto a single row that a student
  cannot use to do harm, so a limiter here would double the write load on the one
  path that cannot be degraded on event day, to prevent nothing.
- **Submit.** A repeat submit is a row lock and a read of a result already
  computed. There is nothing to abuse, and a limit that fires has blocked a real
  student from handing in a real exam. An impatient double-click is not an attack.

Only *failed* admin logins count towards the brute-force budget. Counting
successes would lock out an admin signing in from a phone and a laptop — the
limiter causing the incident it exists to prevent. The limiter also **fails
open**: if it cannot reach the database it lets the request through, because an
outage in a protective mechanism must never stop students sitting the exam.

### Integrity signals

Read spec §1.2 before extending these. Tab-switch and fullscreen-exit detection
catches a student who alt-tabs on the same device and *nothing else* — not a
second device, not a phone, not a shared screen, not a person sitting next to
them. Two server-side signals carry more information, and both are computed
post-hoc from data the student cannot edit:

- `fast_response` — several correct answers returned faster than the question can
  be read. One quick answer is luck; the threshold exists so the list is short
  enough to actually be read.
- `pattern_match` — two students whose entire answer sequence is identical. A
  `GROUP BY` on a hash, not a pairwise scan: at slot capacity the naive version
  is 12.5 million comparisons. All-blank papers are excluded, because several
  students who answered nothing is absence, not collusion.

Nothing here disqualifies anyone or changes a score — there is a test asserting
exactly that. They produce a list at `/admin` for a human. Rescanned hourly by
cron and on demand from the admin panel; a rescan replaces its own flags rather
than piling up duplicates.

### Errors

`SENTRY_DSN` is optional. Unset, errors still reach the platform log — Sentry
adds grouping and alerting, not the record itself. PII is off (`send_default_pii`
is false): student phone numbers pass through these requests, and errors are for
debugging, not for copying the roster to another vendor. Traces default to 0%,
because at slot capacity a 10% sample of the autosave path is millions of spans
nobody reads.

### Load and soak

`scripts/loadtest/` holds k6 scripts for the two paths that actually break —
exam start and autosave — with thresholds that fail the run rather than printing
a number to squint at, including a **zero-tolerance check that one student never
gets two attempts under concurrency**. See `scripts/loadtest/README.md`.

`pnpm soak` drives many complete exams through the real HTTP API and then checks
the invariants in the database rather than trusting the responses that produced
them: no double attempts, every finished attempt scored and certificated, no
certificate ID collisions, and stored scores still agreeing with stored answers.

Both need a scratch Supabase project — they use the symmetric JWT path, which
`settings.py` refuses in production outright. That refusal is doing its job:
you should not be able to point these at the real event.

## Question bank

```bash
pnpm bank:check                          # can each domain serve the blueprint?
pnpm bank:audit                          # measure what selection actually does
pnpm bank:import data/questions/*.csv    # all-or-nothing per file
pnpm bank:export ai-ml > ai-ml.csv       # round-trips back into import
```

Import validates before it writes: a file with one bad row imports nothing, so
you fix the spreadsheet rather than hunting for which half landed. It rejects
the failures that silently mis-score students — two identical options, a
correct letter past the end of the options, a missing explanation, a duplicate
`external_id` — and any file where one letter holds more than 40% of the
answers. `scripts/balance_answers.py` fixes that last one by rotating options.

`external_id` is the idempotency key: re-importing an edited sheet updates in
place instead of duplicating the bank. Export and import round-trip exactly —
answer keys, question status and multi-line code snippets all survive, which is
verified rather than assumed.

`bank:check` predicts overlap from pool sizes; `bank:audit` measures it by
generating papers. On the seed bank two students share ~1.4 of their 15
questions and the blueprint is exact on every paper. Re-run the audit after
replacing the bank — the prediction assumes uniform topics and a real bank
never is.

Author new questions in the `~~`-delimited staging format and convert with
`scripts/psv2csv.py`, which handles CSV quoting. Editing the CSV directly is
fine too — the validator will catch a mis-quoted row.

## Tests

```bash
pnpm db:test      # schema constraints, against a scratch Postgres
pnpm api:test     # registration flow end to end
```

Both create and drop their own database; they need a local `psql` that can
`createdb`. `db:test` is the one that proves the one-attempt rule is enforced by
the database rather than by application code.

## Layout

```
src/app/          Next.js routes
src/lib/          Supabase clients, API client
server/           FastAPI application (the real backend)
api/index.py      Vercel entrypoint; imports server/
supabase/         migrations + schema tests
docs/             design spec
```
