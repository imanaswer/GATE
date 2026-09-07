#!/usr/bin/env bash
# Applies the migrations to a scratch database and asserts the constraints hold.
set -euo pipefail
DB="tech_arena_test_$$"
cd "$(dirname "$0")/../.."
dropdb --if-exists "$DB" 2>/dev/null || true
createdb "$DB"
trap 'dropdb --if-exists "$DB" >/dev/null 2>&1 || true' EXIT
psql -q -v ON_ERROR_STOP=1 -d "$DB" -c 'create extension if not exists pgcrypto;'
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f supabase/test/00_auth_shim.sql
for f in supabase/migrations/*.sql; do
  psql -q -v ON_ERROR_STOP=1 -d "$DB" -f "$f"
done
psql -v ON_ERROR_STOP=1 -d "$DB" -f supabase/test/schema_test.sql
echo
echo "schema OK"
