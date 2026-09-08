-- Phase 7 — hardening.

-- Fixed-window counters. One row per (key, window), upserted per request on the
-- paths that are limited.
--
-- Deliberately in Postgres rather than Upstash: the endpoints that need limiting
-- are all low-volume, and the limiter is *cheaper than the thing it protects* —
-- one single-row upsert versus the five-table join behind /verify — so it lowers
-- total database work under abuse rather than amplifying it.
--
-- ponytail: fixed window, so a burst straddling a boundary can reach 2× the
-- limit briefly. Move to a sliding window log if that ever matters; for
-- brute-force and scraping it does not.
create table rate_limits (
  bucket        text        not null,      -- e.g. 'admin_login', 'verify'
  subject       text        not null,      -- IP, admin id, attempt id
  window_start  timestamptz not null,
  count         integer     not null default 0,
  primary key (bucket, subject, window_start)
);
-- Old windows are swept by the existing attempt-expiry cron; without an index
-- that sweep degrades into a scan as the table grows.
create index rate_limits_window_idx on rate_limits (window_start);

-- The integrity scan hashes each attempt's ordered answer sequence and groups
-- on it; without this the group-by re-sorts every answer row in the database.
create index answers_sequence_idx on answers (attempt_id, attempt_question_id);

alter table rate_limits enable row level security;
