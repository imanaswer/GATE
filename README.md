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

**Phases 1–5 complete** — auth, registration, the one-attempt constraint, the
question bank, the exam engine (blueprint selection, server-authoritative
timer, autosave, resume, idempotent submit, backend scoring), the student UI end
to end, and participation certificates. Phases 6–7 (admin, hardening) are in the
spec's build order.

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
