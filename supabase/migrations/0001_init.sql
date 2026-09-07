-- Tech Arena — initial schema
-- Access model: students NEVER touch PostgREST. RLS is enabled with no policies
-- on every table, so the anon/authenticated keys can read nothing. FastAPI holds
-- a direct connection as the owner role and bypasses RLS. This is the single most
-- important line of defence in the schema: without it, Supabase's auto-generated
-- REST API would happily serve question_options.is_correct to any logged-in student.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- identity

create table colleges (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  city        text,
  state       text,
  created_at  timestamptz not null default now()
);
create unique index colleges_name_key on colleges (lower(name));

create table users (
  id             uuid primary key references auth.users (id) on delete cascade,
  email          text not null,
  name           text not null,
  phone          text,
  college_id     uuid references colleges (id) on delete set null,
  course         text,
  academic_year  smallint check (academic_year between 1 and 6),
  student_id     text,
  registered_at  timestamptz,           -- null until the profile form is completed
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create unique index users_email_key on users (lower(email));
-- Advisory only. Deliberately NOT unique: a mistyped register number must never
-- lock the student who actually owns it out of the event. Collisions are detected
-- in app code and written to suspicious_activity for a human to resolve.
create index users_college_student_idx on users (college_id, student_id)
  where student_id is not null;

create table admin_users (
  id             uuid primary key default gen_random_uuid(),
  email          text not null,
  name           text not null,
  role           text not null default 'viewer' check (role in ('admin', 'viewer')),
  password_hash  text not null,
  last_login_at  timestamptz,
  created_at     timestamptz not null default now()
);
create unique index admin_users_email_key on admin_users (lower(email));

-- ---------------------------------------------------------------- content

create table domains (
  id           uuid primary key default gen_random_uuid(),
  slug         text not null unique,
  name         text not null,
  icon         text,
  description  text,
  position     smallint not null default 0,
  is_active    boolean not null default true
);

create table questions (
  id            uuid primary key default gen_random_uuid(),
  domain_id     uuid not null references domains (id) on delete restrict,
  type          text not null check (type in ('mcq','code_output','debug','scenario','logic')),
  body          text not null,
  code_snippet  text,
  language      text,
  topic         text not null,
  difficulty    text not null check (difficulty in ('easy','medium','hard')),
  explanation   text,
  status        text not null default 'draft' check (status in ('draft','active','retired')),
  version       integer not null default 1,
  created_by    uuid references admin_users (id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
-- Covers the hot selection query: active questions for a domain, by difficulty.
create index questions_pool_idx on questions (domain_id, difficulty, status)
  where status = 'active';

create table question_options (
  id           uuid primary key default gen_random_uuid(),
  question_id  uuid not null references questions (id) on delete cascade,
  body         text not null,
  is_correct   boolean not null default false,
  position     smallint not null,
  unique (question_id, position)
);
create index question_options_question_idx on question_options (question_id);

-- Exactly one correct option per question. Enforced in the database because a
-- question with zero or two correct answers silently mis-scores every student
-- who receives it, and nobody notices until after the event.
create unique index question_options_one_correct_idx
  on question_options (question_id) where is_correct;

-- ---------------------------------------------------------------- event + attempts

create table exam_events (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  slug              text not null unique,
  duration_seconds  integer not null default 1200 check (duration_seconds between 60 and 21600),
  blueprint         jsonb not null default '{"easy":5,"medium":7,"hard":3}'::jsonb,
  opens_at          timestamptz,
  closes_at         timestamptz,
  is_active         boolean not null default true,
  created_at        timestamptz not null default now()
);

create table exam_attempts (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references users (id) on delete cascade,
  event_id       uuid not null references exam_events (id) on delete cascade,
  domain_id      uuid not null references domains (id) on delete restrict,
  status         text not null default 'in_progress'
                   check (status in ('in_progress','submitted','expired')),
  started_at     timestamptz not null default now(),
  expires_at     timestamptz not null,
  submitted_at   timestamptz,
  score          smallint,
  correct_count  smallint,
  wrong_count    smallint,
  skipped_count  smallint,
  session_token  uuid not null default gen_random_uuid(),
  ip             inet,
  user_agent     text,
  -- THE one-attempt rule. Not a check in application code, not a localStorage
  -- flag: a database constraint that concurrent requests cannot race past.
  unique (user_id, event_id)
);
create index exam_attempts_event_status_idx on exam_attempts (event_id, status);
create index exam_attempts_domain_status_idx on exam_attempts (domain_id, status);
create index exam_attempts_expiry_idx on exam_attempts (expires_at)
  where status = 'in_progress';

create table attempt_questions (
  id            uuid primary key default gen_random_uuid(),
  attempt_id    uuid not null references exam_attempts (id) on delete cascade,
  question_id   uuid not null references questions (id) on delete restrict,
  position      smallint not null check (position between 1 and 100),
  option_order  uuid[] not null,        -- frozen per-attempt shuffle
  unique (attempt_id, position),
  unique (attempt_id, question_id)      -- no question twice in one attempt
);

create table answers (
  id                   uuid primary key default gen_random_uuid(),
  attempt_id           uuid not null references exam_attempts (id) on delete cascade,
  attempt_question_id  uuid not null references attempt_questions (id) on delete cascade,
  selected_option_id   uuid references question_options (id) on delete set null, -- null = skipped
  is_correct           boolean,          -- server-computed at submit
  response_ms          integer,          -- client-reported; advisory, spoofable
  answered_at          timestamptz not null default now(),
  unique (attempt_question_id)           -- upsert target: autosave is idempotent
);
create index answers_attempt_idx on answers (attempt_id);

-- ---------------------------------------------------------------- output + safety

create table certificates (
  id                uuid primary key default gen_random_uuid(),
  attempt_id        uuid not null unique references exam_attempts (id) on delete cascade,
  certificate_id    text not null unique,   -- TA-2026-XXXXXXXXXX, random not sequential
  verify_hash       text not null,
  issued_at         timestamptz not null default now(),
  pdf_path          text,                   -- null until first download renders it
  pdf_generated_at  timestamptz
);

create table suspicious_activity (
  id           uuid primary key default gen_random_uuid(),
  attempt_id   uuid references exam_attempts (id) on delete cascade,
  user_id      uuid references users (id) on delete cascade,
  type         text not null check (type in (
                 'tab_switch','fullscreen_exit','disconnect','session_takeover',
                 'duplicate_student_id','fast_response','pattern_match')),
  detail       jsonb not null default '{}'::jsonb,
  occurred_at  timestamptz not null default now()
);
create index suspicious_activity_attempt_idx on suspicious_activity (attempt_id);
create index suspicious_activity_user_idx on suspicious_activity (user_id);

create table jobs (
  id           uuid primary key default gen_random_uuid(),
  kind         text not null,
  params       jsonb not null default '{}'::jsonb,
  status       text not null default 'queued' check (status in ('queued','running','done','failed')),
  result_path  text,
  error        text,
  created_at   timestamptz not null default now(),
  finished_at  timestamptz
);
create index jobs_status_idx on jobs (status, created_at);

-- ---------------------------------------------------------------- lockdown

alter table colleges            enable row level security;
alter table users               enable row level security;
alter table admin_users         enable row level security;
alter table domains             enable row level security;
alter table questions           enable row level security;
alter table question_options    enable row level security;
alter table exam_events         enable row level security;
alter table exam_attempts       enable row level security;
alter table attempt_questions   enable row level security;
alter table answers             enable row level security;
alter table certificates        enable row level security;
alter table suspicious_activity enable row level security;
alter table jobs                enable row level security;
-- No policies, by design. Every read and write goes through FastAPI.
