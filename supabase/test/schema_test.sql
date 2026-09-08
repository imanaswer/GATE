-- Proves the constraints that matter actually hold. Run: pnpm db:test
\set ON_ERROR_STOP on
\set QUIET on

begin;

-- fixtures
insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111', 'asha@example.edu'),
  ('22222222-2222-2222-2222-222222222222', 'ravi@example.edu');
insert into colleges (id, name) values ('aaaaaaaa-0000-0000-0000-000000000001', 'ABC College');
insert into users (id, email, name, college_id, student_id, registered_at) values
  ('11111111-1111-1111-1111-111111111111', 'asha@example.edu', 'Asha',
   'aaaaaaaa-0000-0000-0000-000000000001', 'CS21001', now()),
  ('22222222-2222-2222-2222-222222222222', 'ravi@example.edu', 'Ravi',
   'aaaaaaaa-0000-0000-0000-000000000001', 'CS21002', now());

\echo '--- 1. one attempt per user per event'
insert into exam_attempts (user_id, event_id, domain_id, expires_at)
select '11111111-1111-1111-1111-111111111111', e.id, d.id, now() + interval '20 min'
from exam_events e, domains d where e.slug='tech-arena-2026' and d.slug='ai-ml';

do $$
begin
  insert into exam_attempts (user_id, event_id, domain_id, expires_at)
  select '11111111-1111-1111-1111-111111111111', e.id, d.id, now() + interval '20 min'
  from exam_events e, domains d where e.slug='tech-arena-2026' and d.slug='full-stack';
  raise exception 'FAIL: a second attempt was accepted';
exception when unique_violation then
  raise notice 'PASS: second attempt rejected by the database';
end $$;

\echo '--- 2. a different student may still start'
insert into exam_attempts (user_id, event_id, domain_id, expires_at)
select '22222222-2222-2222-2222-222222222222', e.id, d.id, now() + interval '20 min'
from exam_events e, domains d where e.slug='tech-arena-2026' and d.slug='ai-ml';
\echo 'PASS: unrelated student unaffected'

\echo '--- 3. duplicate (college, student_id) is allowed, so it can be FLAGGED not blocked'
insert into auth.users (id, email) values ('33333333-3333-3333-3333-333333333333','typo@example.edu');
insert into users (id, email, name, college_id, student_id, registered_at) values
  ('33333333-3333-3333-3333-333333333333','typo@example.edu','Typo Student',
   'aaaaaaaa-0000-0000-0000-000000000001','CS21001', now());
\echo 'PASS: duplicate register number registered (app flags it for review)'

\echo '--- 4. a question cannot have two correct options'
insert into questions (id, domain_id, type, body, topic, difficulty, status)
select 'bbbbbbbb-0000-0000-0000-000000000001', d.id, 'mcq', 'Q?', 'basics', 'easy', 'active'
from domains d where d.slug='ai-ml';
insert into question_options (question_id, body, is_correct, position) values
  ('bbbbbbbb-0000-0000-0000-000000000001','right', true, 1),
  ('bbbbbbbb-0000-0000-0000-000000000001','wrong', false, 2);
do $$
begin
  insert into question_options (question_id, body, is_correct, position)
  values ('bbbbbbbb-0000-0000-0000-000000000001','also right', true, 3);
  raise exception 'FAIL: two correct options were accepted';
exception when unique_violation then
  raise notice 'PASS: second correct option rejected';
end $$;

\echo '--- 5. autosave is idempotent (one row per attempt_question)'
insert into attempt_questions (id, attempt_id, question_id, position, option_order)
select 'cccccccc-0000-0000-0000-000000000001', a.id, 'bbbbbbbb-0000-0000-0000-000000000001', 1,
       array(select id from question_options where question_id='bbbbbbbb-0000-0000-0000-000000000001')
from exam_attempts a where a.user_id='11111111-1111-1111-1111-111111111111';

insert into answers (attempt_id, attempt_question_id, selected_option_id)
select a.id, 'cccccccc-0000-0000-0000-000000000001', o.id
from exam_attempts a, question_options o
where a.user_id='11111111-1111-1111-1111-111111111111'
  and o.question_id='bbbbbbbb-0000-0000-0000-000000000001' and o.position=1
on conflict (attempt_question_id) do update set selected_option_id = excluded.selected_option_id;

insert into answers (attempt_id, attempt_question_id, selected_option_id)
select a.id, 'cccccccc-0000-0000-0000-000000000001', o.id
from exam_attempts a, question_options o
where a.user_id='11111111-1111-1111-1111-111111111111'
  and o.question_id='bbbbbbbb-0000-0000-0000-000000000001' and o.position=2
on conflict (attempt_question_id) do update set selected_option_id = excluded.selected_option_id;

do $$
declare n int;
begin
  select count(*) into n from answers
  where attempt_question_id = 'cccccccc-0000-0000-0000-000000000001';
  if n <> 1 then raise exception 'FAIL: % answer rows, expected 1', n; end if;
  raise notice 'PASS: re-saving an answer updates in place, never duplicates';
end $$;

\echo '--- 6. every table has RLS on, with no policies'
do $$
declare bad text;
begin
  -- The schema's own most important line of defence: RLS enabled with no
  -- policies means the anon and authenticated keys can read nothing through
  -- PostgREST, and every read goes through FastAPI instead. Checked across all
  -- tables rather than a list, so a table added later cannot quietly miss it.
  select string_agg(c.relname, ', ' order by c.relname) into bad
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity;
  if bad is not null then
    raise exception 'FAIL: tables without row level security: %', bad;
  end if;
  raise notice 'PASS: row level security is on for every table';

  select string_agg(distinct p.tablename, ', ') into bad
  from pg_policies p where p.schemaname = 'public';
  if bad is not null then
    raise exception 'FAIL: unexpected RLS policies on: %', bad;
  end if;
  raise notice 'PASS: no table grants a policy to the anon key';
end $$;

rollback;
