-- Collect less. The registration form now asks for phone, location, college and
-- an optional student ID; name and email still come from the verified Google
-- token and are never accepted from the client.
--
-- Course and academic year are dropped rather than left nullable: a column we
-- never populate is not "collecting less", it is the same form with hidden
-- fields. Safe to drop here because no event has run — do NOT replay this on a
-- database that holds real attempts without exporting first.
alter table users drop column if exists course;
alter table users drop column if exists academic_year;

-- Mirrors `colleges` exactly, for the same reason: free-text entry is allowed,
-- but "Kochi" and "kochi " must not become two rows in the analytics. Keeping
-- it a table rather than a text column on users also means the autocomplete
-- reads a small dimension instead of scanning every student on each keystroke.
create table locations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);
create unique index locations_name_key on locations (lower(name));

alter table users add column location_id uuid references locations (id) on delete set null;
create index users_location_idx on users (location_id);

alter table locations enable row level security;
