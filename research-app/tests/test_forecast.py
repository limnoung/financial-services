from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

np = pytest.importorskip("numpy")
pl = pytest.importorskip("polars")
pytest.importorskip("dartlab")

from gems_research import forecast
from gems_research.models import ForecastInput, today_kst
from gems_research.server import app


def observations(count=600):
    days, current = [], today_kst()
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    days.reverse()
    prices = (100 * np.exp(np.cumsum(np.random.default_rng(29).normal(0.0002, .012, count)))).tolist()
    return days, prices


def frame(count=600):
    days, values = observations(count)
    changes = [0.0] + [(b / a - 1) * 100 for a, b in zip(values, values[1:])]
    return pl.DataFrame({"BAS_DD": [d.strftime("%Y%m%d") for d in days], "ISU_CD": ["005930"] * count,
                         "TDD_CLSPRC": values, "FLUC_RT": changes})


@pytest.mark.parametrize("method", ["ar1", "drift"])
@pytest.mark.parametrize("horizon", [5, 20, 60])
def test_forecast_horizons_have_ordered_bands_and_nonoverlapping_validation(method, horizon):
    days, values = observations(1000)
    result = forecast.forecast_series(days, values, ForecastInput(symbol="005930", horizon=horizon, method=method), source="test")
    assert len(result["future"]) == horizon
    assert [p["step"] for p in result["future"]] == list(range(1, horizon + 1))
    assert all(0 < p["lower"] <= p["estimate"] <= p["upper"] for p in result["future"])
    assert result["calibration"]["count"] == 252
    rows = result["validation"]["rows"]
    assert len(rows) == 6
    assert all(a["target"] <= b["origin"] for a, b in zip(rows, rows[1:]))
    assert result["validation"]["calibration"]["cutoff"] == rows[0]["origin"]
    assert all(row["origin"] < row["target"] for row in rows)


def test_model_fit_does_not_consume_later_prices():
    _, prices = observations(500)
    first = forecast.model_path(prices, 200, 126, 20, "ar1")
    changed = prices[:201] + [value * 10 for value in prices[201:]]
    np.testing.assert_allclose(first, forecast.model_path(changed, 200, 126, 20, "ar1"))


def test_validation_bands_and_first_prediction_do_not_use_holdout_targets():
    days, values = observations(600)
    request = ForecastInput(symbol="005930")
    original = forecast.forecast_series(days, values, request, source="test")
    first = original["validation"]["rows"][0]
    origin = days.index(date.fromisoformat(first["origin"]))
    changed = values[:origin + 1] + [v * 1.1 for v in values[origin + 1:]]
    new_first = forecast.forecast_series(days, changed, request, source="test")["validation"]["rows"][0]
    for key in ("origin", "target", "estimate", "lower", "upper"):
        assert first[key] == new_first[key]
    assert first["actual"] != new_first["actual"]


def test_known_log_trend_has_analytic_forecast_and_beats_flat_baseline():
    days, _ = observations(600)
    prices = (100 * np.exp(.001 * np.arange(600))).tolist()
    result = forecast.forecast_series(days, prices, ForecastInput(symbol="005930", method="drift"), source="test")
    assert result["future"][-1]["estimate"] == pytest.approx(prices[-1] * np.exp(.02))
    assert result["validation"]["mape"] < 1e-9
    assert result["validation"]["relative_mae"] < 1e-9
    assert result["validation"]["baseline_mape"] > 0


def test_flat_series_does_not_divide_by_zero_in_validation():
    days, _ = observations(600)
    result = forecast.forecast_series(days, [100.] * 600, ForecastInput(symbol="005930"), source="test")
    assert all(p["estimate"] == 100 and p["lower"] == 100 and p["upper"] == 100 for p in result["future"])
    assert result["validation"]["relative_mae"] is None
    assert result["validation"]["mape"] == 0


def test_insufficient_calibration_never_invents_an_error_band_or_validation():
    days, prices = observations(127)
    result = forecast.forecast_series(days, prices, ForecastInput(symbol="005930"), source="test")
    assert all(p["lower"] is None and p["upper"] is None for p in result["future"])
    assert result["validation"]["count"] == 0
    assert result["validation"]["interval_coverage"] is None
    assert any("부족" in w for w in result["warnings"])


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 0, -1])
def test_invalid_prices_are_rejected(invalid):
    days, prices = observations(150)
    prices[50] = invalid
    with pytest.raises(ValueError):
        forecast.forecast_series(days, prices, ForecastInput(symbol="005930"), source="test")


def test_too_short_or_future_dated_series_is_rejected():
    days, prices = observations(100)
    with pytest.raises(ValueError, match="127"):
        forecast.forecast_series(days, prices, ForecastInput(symbol="005930"), source="test")
    days, prices = observations(200)
    with pytest.raises(ValueError, match="기준일 이후"):
        forecast.forecast_series(days, prices, ForecastInput(symbol="005930", as_of=days[-5]), source="test")


def test_future_split_is_filtered_before_adjustment():
    raw = frame(300)
    cutoff = date.fromisoformat(raw["BAS_DD"][-20][:4] + "-" + raw["BAS_DD"][-20][4:6] + "-" + raw["BAS_DD"][-20][6:])
    request = ForecastInput(symbol="005930", as_of=cutoff)
    original = forecast.prepare_prices(raw, request)
    changed = raw.with_columns(pl.when(pl.col("BAS_DD") > cutoff.strftime("%Y%m%d")).then(pl.col("TDD_CLSPRC") / 50).otherwise(pl.col("TDD_CLSPRC")).alias("TDD_CLSPRC"))
    revised = forecast.prepare_prices(changed, request)
    assert original == revised
    assert original[0][-1] == cutoff


def test_duplicate_dates_mixed_companies_and_missing_adjustment_inputs_are_rejected():
    raw = frame(160)
    request = ForecastInput(symbol="005930")
    for invalid in (pl.concat([raw, raw.tail(1)]), raw.with_columns(pl.lit("000660").alias("ISU_CD")), raw.drop("FLUC_RT")):
        with pytest.raises(ValueError):
            forecast.prepare_prices(invalid, request)


def test_us_artifact_schema_uses_provider_adjusted_close():
    days, prices = observations(200)
    raw = pl.DataFrame({"date": [d.strftime("%Y%m%d") for d in days], "close": prices})
    actual_days, actual_prices, basis = forecast.prepare_prices(raw, ForecastInput(symbol="AAPL", market="US"))
    assert actual_days == days and actual_prices == prices
    assert "수정종가" in basis


def test_long_price_gap_is_not_silently_counted_as_one_trading_day():
    raw = frame(200)
    with pytest.raises(ValueError, match="공백"):
        forecast.prepare_prices(pl.concat([raw.head(80), raw.tail(80)]), ForecastInput(symbol="005930"))


def test_demo_api_is_reproducible_marked_synthetic_and_does_not_load_company(monkeypatch):
    monkeypatch.setattr(forecast, "load_prices", lambda *args: pytest.fail("demo must not download prices"))
    client = TestClient(app)
    input_data = dict(symbol="005930", demo=True, horizon=20)
    a = client.post("/api/forecast", json=input_data)
    b = client.post("/api/forecast", json=input_data)
    assert a.status_code == 200
    assert a.json() == b.json()
    assert a.json()["symbol"] == "DEMO" and a.json()["demo"]
    assert a.json()["source"]["url"] == ""
    assert "가상" in a.json()["warnings"][0]
    assert "forecast.js" in client.get("/").text
    assert client.get("/static/forecast.js").status_code == 200


def test_api_uses_price_only_loader_and_preserves_offline_policy(monkeypatch):
    calls = []
    monkeypatch.setattr(forecast, "load_prices", lambda *args: calls.append(args) or frame(500))
    response = TestClient(app).post("/api/forecast", json=dict(symbol="005930", market="KR", offline=True))
    assert response.status_code == 200
    assert calls == [("005930", "KR", True)]
    assert response.json()["demo"] is False


def test_actual_dartlab_cache_loader_runs_offline_without_financial_files(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    folder = root / "gov/prices/company"
    folder.mkdir(parents=True)
    frame(500).write_parquet(folder / "005930.parquet")
    monkeypatch.setenv("GEMS_DARTLAB_DATA_DIR", str(root))
    from dartlab.core import dataLoader
    monkeypatch.setattr(dataLoader, "_downloadWithRetry", lambda *args: pytest.fail("offline loader must not download"))
    result = forecast.forecast_prices(ForecastInput(symbol="005930", offline=True))
    assert result["symbol"] == "005930"
    assert result["calibration"]["count"] >= 30
    assert result["validation"]["count"] >= 3
    assert not (root / "dart/finance").exists()


def test_api_errors_on_missing_cache_invalid_horizon_and_future_cutoff(monkeypatch):
    def missing(*args):
        raise FileNotFoundError("local cache missing")
    monkeypatch.setattr(forecast, "load_prices", missing)
    client = TestClient(app)
    assert client.post("/api/forecast", json={"symbol": "005930", "offline": True}).status_code == 422
    assert client.post("/api/forecast", json={"symbol": "005930", "horizon": 200}).status_code == 422
    assert client.post("/api/forecast", json={"symbol": "005930", "as_of": (today_kst() + timedelta(days=1)).isoformat()}).status_code == 422
