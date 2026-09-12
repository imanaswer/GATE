-- The product is now GATE (G-TEC Aptitude Test for Excellence). The slug stays:
-- it is EVENT_SLUG in every environment and nothing user-facing shows it.
update exam_events set name = 'GATE 2026' where slug = 'tech-arena-2026';
