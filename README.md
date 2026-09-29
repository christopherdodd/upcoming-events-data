# Upcoming Events — fixture data

Fixture list read by the Upcoming Events iOS app (a personal project).

`fixtures.json` fields per event:

| Field | Meaning |
|---|---|
| `id` | Stable id: listed date + slug of the title |
| `category` | App category id, e.g. `aus-cricket`, `ufc` |
| `sport` | Label shown on the row, e.g. `Cricket` |
| `title`, `venue` | Display text |
| `start` / `end` | UTC start time (and last day's start for multi-day events), ISO 8601 |
| `date` / `endDate` | Used instead of `start`/`end` when the start time is TBC: the listed date(s), `yyyy-MM-dd` |

Rules: real fixtures only, men's fixtures for international team sports, and `date` (time TBC) rather than a guessed time.

## Daily check

`.github/workflows/daily-check.yml` runs `scripts/check_cricket.py` every day at 22:00 UTC (6 AM WITA).
It compares [CricketData.org](https://cricketdata.org) with `fixtures.json` and keeps one open issue,
**Fixture check: cricket**, listing new matches, changed dates/times, and newly announced start times.
It never edits `fixtures.json`: API data has errors, so each item is checked against an official source first.

- The API key is the repository secret `CRICKETDATA_API_KEY` (free plan; each run uses ~25 of 100 daily requests).
- To silence an item you've checked and rejected, add its `key` from the report to `check-ignore.json`.
- Run it manually from the Actions tab (“Run workflow”), or locally:
  `CRICKETDATA_API_KEY=... python3 scripts/check_cricket.py`
