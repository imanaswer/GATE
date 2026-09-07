-- Domains and the default event. Idempotent: safe to re-run.

insert into domains (slug, name, icon, description, position) values
  ('ai-ml',        'AI / Machine Learning', '🤖', 'Models, training, evaluation, and the maths under them.', 1),
  ('data-science', 'Data Science',          '📊', 'Statistics, wrangling, analysis, and honest inference.',   2),
  ('full-stack',   'Full Stack Development','💻', 'Frontend, backend, APIs, and everything between.',         3),
  ('cybersecurity','Cybersecurity',         '🔐', 'Threats, defences, cryptography, and secure design.',      4),
  ('cloud-devops', 'Cloud / DevOps',        '☁️', 'Infrastructure, pipelines, containers, and reliability.',  5)
on conflict (slug) do nothing;

insert into exam_events (name, slug, duration_seconds, blueprint)
values ('Tech Arena 2026', 'tech-arena-2026', 1200, '{"easy":5,"medium":7,"hard":3}'::jsonb)
on conflict (slug) do nothing;
