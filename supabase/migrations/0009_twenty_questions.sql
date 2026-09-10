-- 20 questions in the same 20 minutes. duration_seconds is already 1200, so
-- only the blueprint moves; the pace goes from 80s a question to 60s.
update exam_events set blueprint = '{"easy":10,"medium":10}'::jsonb
where slug = 'tech-arena-2026';
