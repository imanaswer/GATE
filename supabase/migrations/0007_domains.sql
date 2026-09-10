-- Domains become subject areas rather than tech tracks. Idempotent.

-- Deactivate rather than delete: questions.domain_id is ON DELETE RESTRICT and
-- the old slugs hold the imported bank. is_active is honoured by GET /domains
-- and by attempt start, so the old five simply stop being offered.
update domains set is_active = false
where slug in ('ai-ml', 'data-science', 'full-stack', 'cybersecurity', 'cloud-devops');

insert into domains (slug, name, icon, description, position) values
  ('general',  'General Knowledge', '🧭', 'Current affairs, reasoning, and general awareness.',   1),
  ('math',     'Mathematics',       '➗', 'Arithmetic, algebra, geometry, and quantitative aptitude.', 2),
  ('science',  'Science',           '🔬', 'Physics, chemistry, and biology fundamentals.',        3),
  ('commerce', 'Commerce',          '📈', 'Accounting, business studies, and economics.',         4),
  ('tech',     'Technology',        '💻', 'Computing, programming, and digital literacy.',        5),
  ('data',     'Data',              '📊', 'Statistics, data interpretation, and analysis.',       6),
  ('combined', 'Combined',          '🎯', 'A mixed paper drawing on every subject above.',        7)
on conflict (slug) do update
  set name = excluded.name,
      icon = excluded.icon,
      description = excluded.description,
      position = excluded.position,
      is_active = true;
