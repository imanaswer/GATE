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

**Phase 1 complete** — auth, registration, and the one-attempt constraint.
Phases 2–7 (question bank, exam engine, student UI, certificates, admin,
hardening) are in the spec's build order.

## Setup

```bash
pnpm install
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env.local     # then fill it in
```

**Supabase**

1. Create a project. Copy the URL and anon key into `.env.local`.
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
