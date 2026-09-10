Banks for the five technology tracks that `0007_domains.sql` deactivated.
Kept because they are ~1,500 reviewed questions, parked out of
`data/questions/` so the default `bank:import` glob and the test fixture do
not pick up rows whose domain is no longer active.

To bring a track back: reactivate its row in `domains`, move the file up one
level, and re-run `pnpm bank:import`.
