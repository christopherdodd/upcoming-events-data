#!/usr/bin/env python3
"""Compare CricketData.org fixtures with fixtures.json and write a Markdown report.

Report only: nothing in fixtures.json is changed. Findings are for a person to verify
against an official source before editing the fixture file.

Usage: CRICKETDATA_API_KEY=... python3 scripts/check_cricket.py [report.md]
Exit code: 0 always (unless the API key is missing); the report says whether anything was found.
Uses roughly 15-25 of the free plan's 100 daily requests.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures.json"
IGNORE = ROOT / "check-ignore.json"
API = "https://api.cricapi.com/v1"

WATCHED = ["Australia", "South Africa", "India", "New Zealand", "England"]
# Series that aren't men's senior internationals.
EXCLUDE = re.compile(
    r"women|\bA\b|under-?19|\bU19\b|lions|domestic|premier league|\bleague\b|"
    r"one-day cup|emerging|\bXI\b|academy|legends|masters",
    re.IGNORECASE,
)
HORIZON_DAYS = 120  # only look at series starting within this many days
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

hits = 0


def api(path, **params):
    global hits
    params["apikey"] = os.environ["CRICKETDATA_API_KEY"]
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)
    hits += 1
    if data.get("status") != "success":
        raise RuntimeError(f"{path}: {data.get('reason', 'request failed')}")
    return data


# MARK: - Series discovery

def parse_series_date(value, fallback_year):
    """Series dates come as '2026-09-24' or 'Sep 24' (no year)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    match = re.match(r"([A-Z][a-z]{2}) (\d{1,2})$", value.strip())
    if match and match.group(1) in MONTHS:
        return date(fallback_year, MONTHS[match.group(1)], int(match.group(2)))
    return None


def series_window(series):
    """Best-effort (start, end) dates; the API omits years on some entries."""
    years = [int(y) for y in re.findall(r"20\d\d", series["name"])]
    name_year = years[0] if years else date.today().year
    start = parse_series_date(series.get("startDate"), name_year)
    if start and start.year < 2000:  # placeholder dates like 1900-01-01
        start = None
    start_year = start.year if start else name_year
    end = parse_series_date(series.get("endDate"), start_year)
    if start and end and end < start:
        end = end.replace(year=end.year + 1)
    return start, end


def relevant_series(today):
    found = {}
    for team in WATCHED:
        offset = 0
        for _ in range(2):  # at most two pages per team
            data = api("series", search=team, offset=offset)
            for series in data["data"]:
                if EXCLUDE.search(series["name"]):
                    continue
                start, end = series_window(series)
                if end and end < today:
                    continue
                if start and start > today + timedelta(days=HORIZON_DAYS):
                    continue
                if not (start or end):
                    continue
                found[series["id"]] = series["name"]
            offset += len(data["data"])
            if offset >= data["info"].get("totalRows", 0) or not data["data"]:
                break
    return found


# MARK: - Matching

def title_parts(title):
    """'South Africa vs Australia — 2nd ODI' -> ({'south africa', 'australia'}, '2nd odi')."""
    teams, _, label = title.partition(" — ")
    label = re.sub(r"\s*\(.*?\)", "", label).strip().lower()
    return frozenset(t.strip().lower() for t in teams.split(" vs ")), label


def api_parts(name):
    """'South Africa vs Australia, 2nd ODI, <series name>' -> same shape as title_parts."""
    parts = name.split(",")
    label = parts[1].strip().lower() if len(parts) > 1 else ""
    return frozenset(t.strip().lower() for t in parts[0].split(" vs ")), label


def fixture_day(event):
    if "start" in event:
        return datetime.fromisoformat(event["start"].replace("Z", "+00:00")).date()
    return date.fromisoformat(event["date"])


def category_for(teams):
    return "aus-cricket" if "australia" in teams else "intl-cricket"


def main():
    if not os.environ.get("CRICKETDATA_API_KEY"):
        sys.exit("CRICKETDATA_API_KEY is not set")
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    now = datetime.now(timezone.utc)
    today = now.date()

    fixtures = json.loads(FIXTURES.read_text())["events"]
    cricket = [e for e in fixtures if e["category"] in ("aus-cricket", "intl-cricket")]
    ignored = set(json.loads(IGNORE.read_text())) if IGNORE.exists() else set()

    by_label = {}
    by_teams_day = {}
    for event in cricket:
        teams, label = title_parts(event["title"])
        by_label[(teams, label)] = event
        by_teams_day[(teams, fixture_day(event))] = event

    new, changed, time_found, empty_series = [], [], [], []
    matched_ids = set()

    for series_id, series_name in sorted(relevant_series(today).items(), key=lambda s: s[1]):
        matches = api("series_info", id=series_id)["data"].get("matchList") or []
        if not matches:
            empty_series.append(series_name)
            continue
        for match in matches:
            when = match.get("dateTimeGMT")
            if not when:
                continue
            start = datetime.fromisoformat(when).replace(tzinfo=timezone.utc)
            if start < now - timedelta(hours=8):
                continue
            teams, label = api_parts(match["name"])
            if not any(t.lower() in teams for t in WATCHED):
                continue
            event = by_label.get((teams, label)) or by_teams_day.get((teams, start.date()))
            line = f"**{match['name']}** · {start:%a %d %b %Y, %H:%M} UTC · {match.get('venue', '?')}"

            if event is None:
                key = f"new:{match['id']}"
                if key not in ignored:
                    new.append((key, f"{line} · category `{category_for(teams)}` · _{series_name}_"))
                continue

            matched_ids.add(event["id"])
            if "start" in event:
                ours = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
                if ours != start:
                    key = f"changed:{event['id']}"
                    if key not in ignored:
                        changed.append((key, f"{line}\n  - fixtures.json has `{event['start']}` (`{event['id']}`)"))
            else:
                if fixture_day(event) != start.date():
                    key = f"changed:{event['id']}"
                    if key not in ignored:
                        changed.append((key, f"{line}\n  - fixtures.json has date `{event['date']}`, time TBC (`{event['id']}`)"))
                else:
                    key = f"time:{event['id']}"
                    if key not in ignored:
                        time_found.append((key, f"{line}\n  - fixtures.json has time TBC (`{event['id']}`)"))

    upcoming = [e for e in cricket if fixture_day(e) >= today]
    unchecked = [e for e in upcoming if e["id"] not in matched_ids]

    lines = [f"_Checked {now:%a %d %b %Y, %H:%M} UTC using {hits} CricketData requests._", ""]
    lines.append("Verify each item against an official source before editing `fixtures.json`. "
                 "To stop an item reappearing, add its key to `check-ignore.json`.")
    for heading, items in [
        ("New matches not in fixtures.json", new),
        ("Date or time differs", changed),
        ("Start time now listed (fixtures.json has TBC)", time_found),
    ]:
        lines += ["", f"## {heading} ({len(items)})"]
        lines += [f"- {text}\n  - key: `{key}`" for key, text in items] or ["None."]
    lines += ["", f"<details><summary>Not checked: {len(unchecked)} upcoming fixtures CricketData had no data for</summary>", ""]
    lines += [f"- {e['title']} (`{e['id']}`)" for e in unchecked] or ["None."]
    if empty_series:
        lines += ["", "Series with no match list yet: " + "; ".join(empty_series)]
    lines += ["", "</details>"]

    report = "\n".join(lines) + "\n"
    findings = len(new) + len(changed) + len(time_found)
    if report_path:
        report_path.write_text(report)
    else:
        print(report)
    print(f"findings={findings} requests={hits}", file=sys.stderr)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"findings={findings}\n")


if __name__ == "__main__":
    main()
