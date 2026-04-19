"""
Unit tests for auton_importance.py (core logic only — no live API calls).
"""

import pytest
from auton_importance import (
    get_auton_points,
    get_total_score,
    analyse_match,
    compute_win_pct_for_range,
    build_summary_table,
    AUTON_DIFF_RANGES,
)


# ---------------------------------------------------------------------------
# Fixtures / helper builders
# ---------------------------------------------------------------------------

def make_match(red_auto, blue_auto, red_total, blue_total):
    """Return a minimal match-like dict."""
    return {
        "score_breakdown": {
            "red": {"autoPoints": red_auto},
            "blue": {"autoPoints": blue_auto},
        },
        "alliances": {
            "red": {"score": red_total},
            "blue": {"score": blue_total},
        },
    }


# ---------------------------------------------------------------------------
# get_auton_points
# ---------------------------------------------------------------------------

class TestGetAutonPoints:
    def test_returns_red_auto(self):
        m = make_match(20, 15, 100, 90)
        assert get_auton_points(m, "red") == 20

    def test_returns_blue_auto(self):
        m = make_match(20, 15, 100, 90)
        assert get_auton_points(m, "blue") == 15

    def test_returns_none_when_score_breakdown_missing(self):
        m = {"alliances": {"red": {"score": 50}, "blue": {"score": 40}}}
        assert get_auton_points(m, "red") is None

    def test_returns_none_when_alliance_key_missing(self):
        m = {"score_breakdown": {"blue": {"autoPoints": 10}}, "alliances": {}}
        assert get_auton_points(m, "red") is None

    def test_returns_none_when_autoPoints_key_missing(self):
        m = {"score_breakdown": {"red": {}, "blue": {"autoPoints": 10}}, "alliances": {}}
        assert get_auton_points(m, "red") is None


# ---------------------------------------------------------------------------
# get_total_score
# ---------------------------------------------------------------------------

class TestGetTotalScore:
    def test_returns_red_score(self):
        m = make_match(20, 15, 100, 90)
        assert get_total_score(m, "red") == 100

    def test_returns_blue_score(self):
        m = make_match(20, 15, 100, 90)
        assert get_total_score(m, "blue") == 90

    def test_returns_none_when_alliances_missing(self):
        m = {"score_breakdown": {}}
        assert get_total_score(m, "red") is None


# ---------------------------------------------------------------------------
# analyse_match
# ---------------------------------------------------------------------------

class TestAnalyseMatch:
    def test_auton_winner_wins_match(self):
        # Red wins auton (25 vs 15 = diff 10) and wins match
        m = make_match(25, 15, 100, 80)
        result = analyse_match(m)
        assert result is not None
        assert result["auton_diff"] == 10
        assert result["auton_winner_won_match"] is True

    def test_auton_winner_loses_match(self):
        # Red wins auton but blue wins overall
        m = make_match(20, 15, 70, 90)
        result = analyse_match(m)
        assert result is not None
        assert result["auton_diff"] == 5
        assert result["auton_winner_won_match"] is False

    def test_auton_tie_excluded(self):
        m = make_match(15, 15, 100, 80)
        assert analyse_match(m) is None

    def test_match_tie_excluded(self):
        m = make_match(20, 15, 90, 90)
        assert analyse_match(m) is None

    def test_missing_data_excluded(self):
        m = {"score_breakdown": {"red": {}, "blue": {"autoPoints": 10}}, "alliances": {}}
        assert analyse_match(m) is None

    def test_auton_diff_is_absolute(self):
        # Blue wins auton; diff should still be positive
        m = make_match(10, 20, 90, 100)
        result = analyse_match(m)
        assert result["auton_diff"] == 10

    def test_exact_one_point_auton_diff(self):
        m = make_match(16, 15, 100, 80)
        result = analyse_match(m)
        assert result["auton_diff"] == 1


# ---------------------------------------------------------------------------
# compute_win_pct_for_range
# ---------------------------------------------------------------------------

class TestComputeWinPctForRange:
    def _records(self, diffs_and_wins):
        """Build records from list of (auton_diff, auton_winner_won_match)."""
        return [{"auton_diff": d, "auton_winner_won_match": w} for d, w in diffs_and_wins]

    def test_all_wins(self):
        records = self._records([(1, True), (1, True), (1, True)])
        pct, n = compute_win_pct_for_range(records, 1, 1)
        assert pct == 100.0
        assert n == 3

    def test_all_losses(self):
        records = self._records([(1, False), (1, False)])
        pct, n = compute_win_pct_for_range(records, 1, 1)
        assert pct == 0.0
        assert n == 2

    def test_mixed(self):
        records = self._records([(3, True), (3, True), (3, False), (3, True)])
        pct, n = compute_win_pct_for_range(records, 2, 5)
        assert pct == 75.0
        assert n == 4

    def test_empty_range(self):
        records = self._records([(1, True), (5, True)])
        pct, n = compute_win_pct_for_range(records, 2, 4)
        assert pct is None
        assert n == 0

    def test_range_boundaries_inclusive(self):
        records = self._records([(6, True), (10, True), (5, False), (11, False)])
        pct, n = compute_win_pct_for_range(records, 6, 10)
        assert n == 2
        assert pct == 100.0


# ---------------------------------------------------------------------------
# build_summary_table
# ---------------------------------------------------------------------------

class TestBuildSummaryTable:
    def test_returns_one_row_per_range(self):
        records = [{"auton_diff": 1, "auton_winner_won_match": True}]
        rows = build_summary_table(records)
        assert len(rows) == len(AUTON_DIFF_RANGES)

    def test_na_when_no_data_in_range(self):
        records = [{"auton_diff": 1, "auton_winner_won_match": True}]
        rows = build_summary_table(records)
        # Only the first bucket (diff == 1) has data; others should be "N/A"
        labels_with_data = [r[0] for r in rows if r[1] != "N/A"]
        assert labels_with_data == ["1"]

    def test_win_pct_formatted_with_percent_sign(self):
        records = [{"auton_diff": 1, "auton_winner_won_match": True}]
        rows = build_summary_table(records)
        assert rows[0][1].endswith("%")

    def test_sample_size_correct(self):
        records = [
            {"auton_diff": 1, "auton_winner_won_match": True},
            {"auton_diff": 1, "auton_winner_won_match": False},
        ]
        rows = build_summary_table(records)
        assert rows[0][2] == 2
