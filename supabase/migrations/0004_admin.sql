-- Phase 6 — admin.

-- Overview counters. A plain table refreshed by cron, deliberately not a
-- materialized view: a matview cannot carry RLS, and RLS-with-no-policies is
-- what keeps PostgREST from serving these tables to anyone holding the anon key.
-- Recomputing this live would also mean COUNT(*) over every attempt on every
-- dashboard load, which would be the slowest thing in the system.
create table admin_overview (
  id             boolean primary key default true check (id),   -- exactly one row
  students       integer not null default 0,
  registered     integer not null default 0,
  attempts       integer not null default 0,
  in_progress    integer not null default 0,
  submitted      integer not null default 0,
  expired        integer not null default 0,
  certificates   integer not null default 0,
  colleges       integer not null default 0,
  flagged        integer not null default 0,
  average_score  numeric(5,2),
  by_domain      jsonb not null default '[]'::jsonb,
  refreshed_at   timestamptz not null default now()
);
insert into admin_overview (id) values (true);

-- Keyset pagination for the student list. OFFSET 40000 is a table scan; this
-- makes (created_at, id) an ordered range the planner can walk.
create index users_keyset_idx on users (created_at, id);

alter table admin_overview enable row level security;
