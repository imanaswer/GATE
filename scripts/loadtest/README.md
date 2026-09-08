# Load tests

Targets from the design spec §2: **1k → 5k → 10k** concurrent, against the two
paths that actually break — exam start and autosave. Everything else is either
low-volume or a read the page cache already serves.

What these are sized for, at slot capacity (5,000 students):

| Path | Shape | Why it is the risk |
|---|---|---|
| `POST /attempts` | ~17/s peak over 5 minutes | `UNIQUE(user_id, event_id)` serialises concurrent starts for one user, and the transaction inserts 15 `attempt_questions` rows |
| `PUT .../answers/{n}` | ~110 writes/s steady | The hot path. One upsert per student per ~45s |

## Running

```bash
brew install k6                      # or https://k6.io/docs/get-started/installation/
export BASE_URL=https://your-preview-deployment.vercel.app
export TOKENS_FILE=/tmp/tokens.json  # see below
k6 run --vus 1000 --duration 20m scripts/loadtest/exam.js

# Smoke run — shape only, not a capacity claim:
THINK_SECONDS=0 k6 run --vus 50 --iterations 50 scripts/loadtest/exam.js
```

`TOKENS_FILE` is a JSON array of Supabase access tokens for pre-registered
throwaway students. **Generate it against a scratch project, never production**
— a load test that registers ten thousand students into the real event fills the
one-attempt table with rows you then have to unpick by hand.

```bash
.venv/bin/python scripts/loadtest/make_tokens.py 1000 > /tmp/tokens.json
```

## Reading the result

The thresholds in `exam.js` fail the run rather than printing a number to
squint at:

- `http_req_failed` under 1%
- start p95 under 3s — a student staring at a spinner assumes it is broken
- autosave p95 under 800ms, because the save indicator is on screen
- **zero** `check` failures on `one_attempt_enforced` — the constraint holding
  under concurrency is the whole point, and a load test that passed while
  double-starting attempts would be worse than no load test

The failure mode to watch for is not CPU. It is connection exhaustion: if
`DATABASE_URL` is not the transaction pooler (port 6543), this falls over long
before 1k.
