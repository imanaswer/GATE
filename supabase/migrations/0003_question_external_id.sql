-- Stable per-domain key so re-importing a spreadsheet UPDATES questions instead
-- of duplicating the bank. Without this, running the importer twice silently
-- doubles every domain and quietly wrecks the difficulty blueprint.
alter table questions add column if not exists external_id text;

create unique index if not exists questions_external_id_key
  on questions (domain_id, external_id) where external_id is not null;
