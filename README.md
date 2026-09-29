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
