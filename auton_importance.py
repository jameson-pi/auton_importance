"""
FRC Autonomous Importance Analyzer
-----------------------------------
Uses the Blue Alliance API (via tbapy) to analyze how winning the
autonomous period correlates with winning the overall match.

Usage:
    python auton_importance.py [year]

If no year is provided, the user is prompted interactively.

The TBA API key can be supplied via the TBA_API_KEY environment variable.
If the variable is not set, the placeholder key below is used as a fallback.
"""

import os
import sys
import csv
import urllib.error
import tbapy

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_PLACEHOLDER_KEY = "8SgFtkRYDT4Awkv91ZkQOohs26hwGjfXlgW9ZQDhbARU49Qlh3da1DRof3GYyaBS"
TBA_API_KEY = os.environ.get("TBA_API_KEY", _PLACEHOLDER_KEY)

# Auton point-difference buckets used for the delta analysis.
# Each entry is (label, low_inclusive, high_inclusive).
AUTON_DIFF_RANGES = [
    ("1",     1,  1),
    ("2-5",   2,  5),
    ("6-10",  6, 10),
    ("11-20", 11, 20),
    ("21+",   21, 9999),
]


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def get_auton_points(match, alliance: str) -> int | None:
    """Return autoPoints for *alliance* ('red' or 'blue'), or None if missing."""
    sb = match.get("score_breakdown") or {}
    alliance_sb = sb.get(alliance) or {}
    val = alliance_sb.get("autoPoints")
    if val is None:
        return None
    return int(val)


def get_total_score(match, alliance: str) -> int | None:
    """Return the final total score for *alliance*, or None if missing."""
    alliances = match.get("alliances") or {}
    alliance_data = alliances.get(alliance) or {}
    val = alliance_data.get("score")
    if val is None:
        return None
    return int(val)


def analyse_match(match):
    """
    Parse a single match and return a dict with:
        auton_diff  – absolute difference in autoPoints (winner minus loser)
        auton_winner_won_match – True/False, or None if excluded (tie)

    Returns None if the match lacks required data.
    """
    red_auto = get_auton_points(match, "red")
    blue_auto = get_auton_points(match, "blue")
    red_total = get_total_score(match, "red")
    blue_total = get_total_score(match, "blue")

    # Skip matches with missing data
    if any(v is None for v in (red_auto, blue_auto, red_total, blue_total)):
        return None

    # Skip auton ties
    if red_auto == blue_auto:
        return None

    # Skip overall match ties
    if red_total == blue_total:
        return None

    auton_diff = abs(red_auto - blue_auto)
    auton_winner_is_red = red_auto > blue_auto
    match_winner_is_red = red_total > blue_total

    return {
        "auton_diff": auton_diff,
        "auton_winner_won_match": auton_winner_is_red == match_winner_is_red,
    }


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def compute_win_pct_for_range(records, low: int, high: int):
    """
    Given a list of analysed-match dicts, filter to those whose auton_diff
    falls in [low, high] and return (win_pct, sample_size).

    Returns (None, 0) when there are no qualifying records.
    """
    subset = [r for r in records if low <= r["auton_diff"] <= high]
    n = len(subset)
    if n == 0:
        return None, 0
    wins = sum(1 for r in subset if r["auton_winner_won_match"])
    return round(wins / n * 100, 1), n


def build_summary_table(records):
    """
    Return a list of rows:
        [range_label, win_pct_str, sample_size]
    one per AUTON_DIFF_RANGES bucket.
    """
    rows = []
    for label, low, high in AUTON_DIFF_RANGES:
        win_pct, n = compute_win_pct_for_range(records, low, high)
        win_pct_str = f"{win_pct}%" if win_pct is not None else "N/A"
        rows.append([label, win_pct_str, n])
    return rows


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def print_summary(rows, year: int, one_point_pct, one_point_n):
    """Pretty-print the analysis results to stdout."""
    header = f"\n{'=' * 55}"
    print(header)
    print(f"  FRC {year} — Autonomous Importance Analysis")
    print(header)

    # One-point spotlight
    print(f"\n  Matches won by exactly 1 auton point:")
    if one_point_n > 0:
        print(f"    Win % when auton winner won full match : {one_point_pct}%")
        print(f"    Sample size (N)                       : {one_point_n}")
    else:
        print("    No qualifying matches found.")

    # Delta analysis table
    print(f"\n  Win % by Auton Score Difference Range")
    print(f"  {'Auton Diff':<14} {'Win %':>8} {'N':>8}")
    print(f"  {'-' * 32}")
    for label, win_pct_str, n in rows:
        print(f"  {label:<14} {win_pct_str:>8} {n:>8}")
    print(header + "\n")


def export_csv(rows, year: int, filename: str):
    """Write the summary table to a CSV file."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Auton Point Diff Range", "Win %", "Sample Size (N)"])
        writer.writerows(rows)
    print(f"  Results exported to: {filename}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_match_data(tba: tbapy.TBA, year: int) -> list:
    """
    Retrieve all qual + playoff match objects for *year* across all events.
    Returns a list of raw match dicts.
    """
    print(f"\nFetching event list for {year}…")
    events = tba.events(year, keys=True)
    total = len(events)
    print(f"Found {total} events. Fetching match data…\n")

    all_matches = []
    for i, event_key in enumerate(events, 1):
        print(f"  [{i:>4}/{total}] {event_key}", end="\r", flush=True)
        try:
            matches = tba.event_matches(event_key)
            all_matches.extend(matches)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
            print(f"\n  Warning: could not fetch {event_key}: {exc}")

    print(f"\nTotal matches fetched: {len(all_matches)}")
    return all_matches


def main(year: int):
    tba = tbapy.TBA(TBA_API_KEY)

    raw_matches = fetch_match_data(tba, year)

    # Analyse every match (skip those missing data or with ties)
    records = []
    for match in raw_matches:
        result = analyse_match(match)
        if result is not None:
            records.append(result)

    print(f"Analysable matches (no ties, complete data): {len(records)}\n")

    # One-point spotlight (exactly 1 auton point difference)
    one_point_pct, one_point_n = compute_win_pct_for_range(records, 1, 1)

    # Full delta-analysis table
    summary_rows = build_summary_table(records)

    # Output
    print_summary(summary_rows, year, one_point_pct, one_point_n)

    csv_filename = f"auton_importance_{year}.csv"
    export_csv(summary_rows, year, csv_filename)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            run_year = int(sys.argv[1])
        except ValueError:
            print(f"Invalid year: {sys.argv[1]}")
            sys.exit(1)
    else:
        raw = input("Enter the FRC season year (e.g. 2024): ").strip()
        try:
            run_year = int(raw)
        except ValueError:
            print(f"Invalid year: {raw}")
            sys.exit(1)

    main(run_year)
