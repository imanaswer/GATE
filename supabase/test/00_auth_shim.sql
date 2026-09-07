-- Stands in for Supabase's auth.users so migrations can be applied to a plain
-- Postgres for testing. Never applied to Supabase itself.
create schema if not exists auth;
create table if not exists auth.users (
  id    uuid primary key default gen_random_uuid(),
  email text
);
