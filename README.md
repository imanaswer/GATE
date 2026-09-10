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
3. Apply the schema: `pnpm db:push`. It uses `MIGRATION_DATABASE_URL` — the
   **session-mode pooler on 5432**, because transaction-mode pooling does not
   reliably run DDL. Use the pooler host, not `db.<ref>.supabase.co`: the direct
   host is IPv6-only on new projects and will simply time out from most laptops
   and CI runners.
   **Percent-encode the password.** A `#`, `@`, `/` or `?` in it will silently
   truncate the URI — `#` in particular makes everything after it a fragment,
   and the failure surfaces as an authentication error rather than a parse one.
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

## Running it, step by step

From a fresh clone to a certificate in your hand. Every command below was run in
this order against an empty database.

### 0. Prerequisites

Node 20+ with `pnpm`, Python 3.13 (`.python-version` pins it), and `psql` on your
PATH. A Supabase project — the student flow is Google sign-in, so there is no
fully offline mode for it. (The exception: `/preview` renders the exam arena from
fixture data with no API and no login, if all you want is to see the screen.)

### 1. Install

```bash
pnpm install
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in `requirements.txt` and adds pytest and uvicorn.
Vercel installs only `requirements.txt`, so test tooling never ships.

### 2. Environment

```bash
cp .env.example .env.local
cp .env.local .env          # yes, both — see the gotcha below
```

Fill in the Supabase values (§ Setup above). **Keep `.env` and `.env.local` in
sync:** `vercel dev` reads `.env.local` for Next.js but passes only **`.env`** to
the Python function, so a value in just one of them produces an API that behaves
differently from the site in front of it.

Minimum to get running locally: `NEXT_PUBLIC_SUPABASE_URL`,
`NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_URL`, `DATABASE_URL`,
`MIGRATION_DATABASE_URL`, `ADMIN_SECRET`, `CRON_SECRET`, `SITE_URL`.
The API logs a warning at boot for each optional one you left blank, so check the
first lines of its output rather than guessing.

### 3. Create the schema

```bash
pnpm db:push
```

Applies every file in `supabase/migrations/` in order and prints each one. Run it
against a **fresh** database — these are plain DDL with no migration ledger, so
re-running on a populated database will stop at the first `create table` that
already exists.

### 4. Seed the question bank

```bash
pnpm bank:import          # all of data/questions/*.csv — 350 questions, 7 domains
pnpm bank:check           # can every domain serve the blueprint?
```

Every domain must come back ✓. If one doesn't, exam start fails for it with a
503, by design — silent degradation here means an unfair exam.

The bank is 50 questions per domain, 25 easy and 25 medium, and the blueprint
is **10 easy + 10 medium** (20 per paper, still 20 minutes — 60s a question).
At that size two students share about **8 of 20** questions; `bank:check` flags
it as *thin*, and `test_papers_differ_between_students` is xfailed against a
4.0 budget. Growing each domain to roughly 160 questions clears both.

⚠️ These seed questions are **public in this repository, answers included**.
Replace them with reviewed questions before a real event: put your CSV in
`data/questions/` and re-run `pnpm bank:import`, or use **Import CSV** in the
admin panel. Import is all-or-nothing, so one bad row imports nothing.

### 5. Create an admin account

```bash
pnpm admin:create you@example.com --role admin    # prompts for a password
pnpm admin:list
```

There is no self-service signup. This needs `DATABASE_URL` in your shell or in
`.env`.

### 6. Start it

Two terminals. The API first:

```bash
.venv/bin/python -m uvicorn server.main:app --port 8100
```

then the site, told where that API is:

```bash
LOCAL_API_URL=http://127.0.0.1:8100 pnpm dev
```

Open **http://localhost:3000**. `next.config.ts` rewrites `/api/v1/*` to
`LOCAL_API_URL`, which is what `vercel.json` does in production — so one server
on one port serves the whole thing. Without that variable the rewrite is inert
and `/api/v1/*` 404s, which is what you want on Vercel, where `vercel.json`
already owns it.

`pnpm dev:full` (`vercel dev`) still works and is closer to production, but it
needs a linked Vercel project and pulls its own environment.

**Do not run `pnpm dev` and `pnpm start` at the same time from this directory.**
They share `.next`, the dev server rewrites the build artifacts underneath the
production server, and the production server then returns 500 for its own CSS —
which looks like a page with no styling rather than an error.

### 7. Walk the flow

| # | Go to | What should happen |
|---|---|---|
| 1 | `/` | Google sign-in |
| 2 | `/register` | Name and email prefilled and read-only; you fill in phone, college, course, year, student ID |
| 3 | `/domains` | Pick one of the five |
| 4 | `/briefing/<slug>` | Rules and timer, then start |
| 5 | `/arena` | 15 questions, 20 minutes. **Refresh mid-exam** — same paper, same answers, timer still counting down from the server |
| 6 | `/complete` | Score, then **Download certificate** |
| 7 | `/verify/<id>` | Public page — open it in a private window to prove it needs no account |
| 8 | `/admin` | Sign in with the account from step 5 |

The one thing worth trying deliberately: **sign in as the same student and start a
second exam.** It is refused by a database constraint, not by app logic.

### 8. Cron jobs, locally

Vercel runs these on a schedule; nothing triggers them on your machine, so the
overview counters read zero and abandoned attempts sit unscored until you call
them yourself:

```bash
for job in expire-attempts refresh-overview scan-integrity; do
  curl -s -X POST localhost:3000/api/v1/cron/$job \
    -H "Authorization: Bearer $CRON_SECRET"; echo
done
```

## Tests

```bash
pnpm api:test     # 154 tests: exam engine, certificates, admin, hardening
pnpm db:test      # constraints and RLS, asserted against real Postgres
pnpm lint && pnpm exec tsc --noEmit && pnpm build
```

`api:test` and `db:test` create and drop their own scratch database, so they need
`psql`, `createdb` and `dropdb` — not your Supabase credentials, and they never
touch your development data. `db:test` is the one that proves the one-attempt
rule and row level security are enforced by the database rather than by
application code.

## Deploying

```bash
vercel link
vercel env add ADMIN_SECRET production      # and the rest of .env.example
vercel --prod
```

`vercel.json` owns the `/api/v1/*` rewrite and the three cron schedules; they
start running on the first production deploy. Set `SITE_URL` to your real domain
**before** anyone sits an exam — it is the origin printed into every certificate
QR code, and a certificate outlives the deployment that issued it.

## What we ask students for

Five things, and three of them are one input each:

| Field | Where it comes from |
|---|---|
| Name | Google, read-only |
| Email | Google, read-only |
| Phone | typed |
| Location | typed, autocompletes from places already entered |
| College | typed, autocompletes from colleges already entered |
| Student ID | typed, **optional** |

Course and academic year were dropped, and `0006` drops the columns rather than
leaving them nullable — a column nobody populates is the same form with hidden
fields, not a shorter one. Name and email are never accepted from the client;
they come from the verified Google token, so nobody registers under someone
else's name.

Student ID stayed because it is the only signal behind the duplicate-register-
number flag (spec §1.1), but it is optional: a student who does not know theirs
must not be blocked from sitting the exam. Two students who both leave it blank
do not flag each other — absent is not a match.

`locations` mirrors `colleges` for the same reason: free text is accepted, but
"Kochi", "kochi" and " Kochi " must be one row in the analytics rather than
three.

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

**Current admin account** (change the password before the event — it is in
version control):

| Email | Password |
|---|---|
| `gtm@gteceducation.com` | `GtecArena@2026!` |

Sign in at `/admin`. Reset it by re-running `pnpm admin:create` with the same
email — `create` upserts.

`ADMIN_SECRET` must be set or the panel refuses to issue a session — never
falls back to a default anyone could forge. Admins sign in at `/admin` against
`admin_users`, not Google: an admin account must not depend on an OAuth app
whose verification status is itself a project risk (spec §10). The session is an
HttpOnly, SameSite=Lax cookie issued by FastAPI, so no token is readable from
JavaScript and enforcement stays in one place — the Next middleware deliberately
does **not** gate `/admin`, because that would mean putting `ADMIN_SECRET` into
the Next runtime too.

Two deletions live on the student detail page, both writer-only and both
logged with the admin's email. **Delete attempt** clears one student's exam so
they can re-sit — one attempt per student is `unique (user_id, event_id)`, a
database constraint, so removing the row is the only way to reopen it. It
cascades away their answers *and their certificate*, so a verification link
already in someone's hands stops working; the panel names the certificate
before you confirm. **Delete student** additionally removes the profile, but
not their Supabase auth account — they can sign in and register again, because
this undoes a mistaken registration rather than banning anyone.

`admin` can write, `viewer` can only read. Questions are **retired, never
deleted** — deleting one would cascade away the `attempt_questions` rows that
explain the score of every student who was given it.

Overview counters come from a one-row `admin_overview` table rather than being
counted live: `COUNT(*)` over every attempt on each dashboard load would be the
slowest thing in the system. The row is recomputed **on read, at most once a
minute**, with the refresh guarded so concurrent admins cannot both trigger it.

That matters because of the plan you deploy on. **Vercel's Hobby plan caps cron
jobs at once per day** (100 jobs, but a minimum interval of 24h, and ±59min
precision) — a per-minute or per-5-minute expression fails the deploy outright.
So nothing user-facing is allowed to depend on cron frequency:

| Job | Cron | What actually keeps it correct |
|---|---|---|
| Overview counters | daily | recomputed on read when older than 60s |
| Expiring abandoned attempts | daily | already lazy on access; plus **Finalise abandoned** in the admin panel |
| Integrity scan | daily | **Re-scan now** in the admin panel |

On Pro you can lower those schedules and the on-read paths simply stop firing.
If you stay on Hobby and want the sweeps to run unattended during the event,
point an external scheduler (a GitHub Actions cron is free) at the same
endpoints with the `CRON_SECRET` bearer token.

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

Missing optional configuration is warned about at boot (`ADMIN_SECRET`,
`SITE_URL`, `CRON_SECRET`), so a misconfigured deploy says so on its first log
line rather than when an organiser tries to sign in on event day.

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

The numbers so far, on one laptop against uvicorn: 200 concurrent students at
~98 req/s, 3400/3400 checks green, zero one-attempt violations, autosave p95
49ms, exam start p95 433ms; then 300 exams through the soak with 300 distinct
certificates and every invariant clean. **That is a shape check, not a capacity
claim.** The tested configuration ran `DB_POOL_MAX=20` against four local
workers; production runs `DB_POOL_MAX=2` against the Supabase transaction
pooler, and connection exhaustion — not CPU — is the failure mode the spec names
as the real risk (§2). Re-run the 1k/5k/10k ladder against a preview deployment
before the event; that is the number that decides whether this holds.

Both need a scratch Supabase project — they use the symmetric JWT path, which
`settings.py` refuses in production outright. That refusal is doing its job:
you should not be able to point these at the real event.

## Question bank

```bash
pnpm bank:check                          # can each domain serve the blueprint?
pnpm bank:audit                          # measure what selection actually does
pnpm bank:import data/questions/*.csv    # all-or-nothing per file
pnpm bank:export math > math.csv       # round-trips back into import
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

## Layout

```
src/app/            Next.js routes (student flow, /admin, /verify)
src/lib/            Supabase clients, API client, exam hook
server/             FastAPI application (the real backend) + its tests
api/index.py        Vercel entrypoint; imports server/
supabase/           migrations + schema tests
scripts/            bank import/export, admin accounts, soak
scripts/loadtest/   k6 load tests
data/questions/     the seed question bank (CSV)
docs/               design spec
```
