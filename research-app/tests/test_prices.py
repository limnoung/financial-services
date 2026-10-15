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
    observations, *_ = _price_observations(price_frame().tail(50))
    assert not observations


def test_duplicate_dates_are_not_accepted_as_more_trading_days():
    frame = price_frame()
    observations, current, *_ = _price_observations(pl.concat([frame, frame.tail(1)]))
    assert not observations and current is None


def test_unadjustable_series_has_price_but_no_momentum_scores():
    observations, current, *_ = _price_observations(price_frame().drop("FLUC_RT"))
    assert current == 1269
    assert not observations
