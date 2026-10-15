from datetime import date, timedelta

import pytest

pl = pytest.importorskip("polars")
pytest.importorskip("dartlab")

from gems_research.data import _price_observations


def price_frame():
    days = []
    current = date(2025, 1, 1)
    while len(days) < 270:
        if current.weekday() < 5:
            days.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    closes = [1000 + i for i in range(len(days))]
    change = [0.0] + [(b / a - 1) * 100 for a, b in zip(closes, closes[1:])]
    return pl.DataFrame({"BAS_DD": days, "ISU_CD": ["005930"] * len(days), "TDD_CLSPRC": closes, "FLUC_RT": change})


def test_price_scoring_requires_full_window_and_retains_adjustment_source():
    observations, current, when, notes = _price_observations(price_frame())
    assert current == 1269
    assert observations["high_distance"].value == 0
    assert observations["trend"].value == "strong_up"
    assert observations["trend"].sources[0].kind == "estimate"
    assert "배당" in observations["trend"].evidence


def test_short_series_is_not_labeled_full_year_or_200_day_trend():
    reasons = {}
    observations, *_ = _price_observations(price_frame().tail(50), diagnostics=reasons)
    assert not observations
    assert "50개" in reasons["trend"] and "220개" in reasons["trend"]


def test_duplicate_dates_are_not_accepted_as_more_trading_days():
    frame = price_frame()
    observations, current, *_ = _price_observations(pl.concat([frame, frame.tail(1)]))
    assert not observations and current is None


def test_unadjustable_series_has_price_but_no_momentum_scores():
    observations, current, *_ = _price_observations(price_frame().drop("FLUC_RT"))
    assert current == 1269
    assert not observations


def test_us_adjusted_artifact_can_score_complete_price_windows():
    frame = price_frame().select(pl.col("BAS_DD").alias("date"), pl.col("TDD_CLSPRC").alias("close"))
    observations, current, *_ = _price_observations(frame, market="US")
    assert current == 1269 and observations["trend"].value == "strong_up"


def test_wrong_symbol_or_missing_split_inputs_does_not_produce_kr_momentum():
    observations, current, *_ = _price_observations(price_frame(), symbol="000660")
    assert not observations and current is None
    reasons = {}
    observations, *_ = _price_observations(price_frame().with_columns(pl.lit(None).cast(pl.Float64).alias("FLUC_RT")), diagnostics=reasons)
    assert not observations and "등락률" in reasons["trend"]


def test_old_gap_outside_required_price_window_does_not_block_recent_momentum():
    recent = price_frame()
    old = recent.head(1).with_columns(pl.lit("20230102").alias("BAS_DD"))
    observations, *_ = _price_observations(pl.concat([old, recent]))
    assert set(observations) == {"trend", "high_distance"}


def test_gap_in_52_week_history_does_not_discard_valid_recent_moving_averages():
    frame = price_frame()
    reasons = {}
    observations, *_ = _price_observations(pl.concat([frame.head(20), frame.slice(40)]), diagnostics=reasons)
    assert set(observations) == {"trend"}
    assert "공백" in reasons["high_distance"]
