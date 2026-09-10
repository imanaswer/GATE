-- The bank is authored easy-to-medium, so a blueprint demanding three hard
-- questions would make select_questions raise BankTooSmall on every start.
-- Paper length stays at 15.
update exam_events set blueprint = '{"easy":7,"medium":8}'::jsonb
where slug = 'tech-arena-2026';
