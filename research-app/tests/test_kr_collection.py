from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

pl = pytest.importorskip("polars")
pytest.importorskip("dartlab")

from gems_research import data
from gems_research.kr_reports import dividend_observation
from gems_research.models import AnalysisInput, Observation, Source
from gems_research.price_history import load_kr_prices
from gems_research.scoring import analyze, numeric_score
from gems_research.rubric import BY_ID
from gems_research.server import app


def reports(start=2020, end=2025):
    rows = []
    for year in range(start, end + 1):
        receipt = f"{year + 1}0310000001"
        for se, kind, value in [("주당 현금배당금(원)", "보통주", str(100 + (year - start) * 10)),
                                 ("현금배당수익률(%)", "보통주", "3.5"),
                                 ("주당액면가액(원)", None, "100"),
                                 ("현금배당수익률(%)", "우선주", "40")]:
            rows.append(dict(apiType="dividend", year=str(year), quarter="4분기", rcept_no=receipt,
                             se=se, stock_knd=kind, thstrm=value, stockCode="005930"))
    return pl.DataFrame(rows)


def prices(count=270):
    days, current = [], date(2025, 1, 1)
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    values = [1000.0 + i for i in range(count)]
    changes = [0.] + [(b / a - 1) * 100 for a, b in zip(values, values[1:])]
    return pl.DataFrame(dict(BAS_DD=days, ISU_CD=["005930"] * count, TDD_CLSPRC=values, FLUC_RT=changes))


def test_ordinary_annual_dividend_has_six_year_growth_and_filing_provenance():
    obs, reason = dividend_observation(reports(), "005930", date(2026, 10, 15))
    assert not reason and obs.value == 3.5
    assert obs.context["regular"] is True
    assert obs.context["growth_years"] == 5
    assert obs.context["cut_recently"] is False
    assert obs.context["dps"] == 150
    assert numeric_score(BY_ID["dividend"], obs) == 5
    assert len(obs.sources) == 6
    assert obs.sources[0].as_of == date(2026, 3, 10)
    assert "현재 주가 기준" in obs.evidence


def test_quarterly_and_future_dividends_never_replace_completed_annual_data():
    rows = reports().to_dicts()
    for row in reports(2025, 2025).to_dicts():
        row.update(quarter="1분기", year="2026", rcept_no="20260515000001", thstrm="999")
        rows.append(row)
    obs, _ = dividend_observation(pl.DataFrame(rows), "005930", date(2026, 2, 1))
    assert obs.context["fiscal_year"] == 2024
    assert obs.context["dps"] == 140
    assert obs.context["growth_years"] == 4


def test_corrected_annual_filing_is_used_without_mixing_original_rows():
    rows = reports().to_dicts()
    corrected = [r.copy() for r in rows if r["year"] == "2025" and r["stock_knd"] != "우선주"]
    for row in corrected:
        row["rcept_no"] = "20260401000001"
        if "주당 현금" in row["se"]:
            row["thstrm"] = "50"
    obs, _ = dividend_observation(pl.DataFrame(rows + corrected), "005930", date(2026, 10, 15))
    assert obs.context["cut_recently"] is True
    assert obs.context["growth_years"] == 0
    assert numeric_score(BY_ID["dividend"], obs) == 2
    assert obs.sources[0].url.endswith("20260401000001")


@pytest.mark.parametrize("change", ["dash", "preferred_only", "par_change", "missing_current_yield"])
def test_ambiguous_dividend_is_missing_instead_of_invented(change):
    rows = reports().to_dicts()
    for row in rows:
        if row["year"] != "2025":
            continue
        if change == "dash" and row["se"] == "주당 현금배당금(원)": row["thstrm"] = "-"
        if change == "preferred_only" and row["stock_knd"] == "보통주": row["stock_knd"] = "우선주"
        if change == "par_change" and row["se"] == "주당액면가액(원)": row["thstrm"] = "50"
        if change == "missing_current_yield" and row["se"] == "현금배당수익률(%)" and row["stock_knd"] == "보통주": row["thstrm"] = None
    obs, reason = dividend_observation(pl.DataFrame(rows), "005930", date(2026, 10, 15))
    assert obs is None and reason


def test_zero_dividend_requires_explicit_zero_values():
    rows = reports(2025, 2025).to_dicts()
    for row in rows:
        if row["stock_knd"] == "보통주": row["thstrm"] = "0"
    obs, _ = dividend_observation(pl.DataFrame(rows), "005930", date(2026, 10, 15))
    assert obs.value == 0 and numeric_score(BY_ID["dividend"], obs) == 1


def test_missing_dividend_history_is_not_classified_as_irregular():
    obs, reason = dividend_observation(reports(2024, 2025), "005930", date(2026, 10, 15))
    assert obs is None and "3개" in reason


def test_non_december_fiscal_year_can_be_published_in_the_same_calendar_year():
    rows = reports(2023, 2025).to_dicts()
    for row in rows:
        row["rcept_no"] = row["year"] + "0610000001"
        row["stlm_dt"] = row["year"] + "-03-31"
    obs, _ = dividend_observation(pl.DataFrame(rows), "005930", date(2026, 10, 15))
    assert obs.context["fiscal_year"] == 2025
    assert obs.sources[0].as_of == date(2025, 6, 10)


def test_matching_krx_history_fills_short_government_window_without_duplicate_days():
    full = prices()
    calls = []
    def load(symbol, category, refresh):
        calls.append((symbol, category, refresh))
        return full.tail(142) if category == "govPriceCompany" else full.head(230)
    merged, notes = load_kr_prices(load, "005930", "local_only")
    assert merged.height == 270 and merged["BAS_DD"].n_unique() == 270
    obs, current, _, _ = data._price_observations(merged, symbol="005930")
    assert set(obs) == {"trend", "high_distance"}
    assert current == 1269 and obs["trend"].value == "strong_up"
    assert all(call[2] == "local_only" for call in calls)
    assert any("보완" in note for note in notes)


def test_mismatched_old_history_cannot_inflate_coverage_or_replace_newest_prices():
    full = prices()
    def load(symbol, category, refresh):
        return full.tail(50) if category == "govPriceCompany" else full.head(250).with_columns(pl.col("TDD_CLSPRC") * 2)
    selected, notes = load_kr_prices(load, "005930", "local_only")
    assert selected.height == 50 and selected["BAS_DD"][-1] == full["BAS_DD"][-1]
    assert data._price_observations(selected)[0] == {}
    assert any("합치지" in note for note in notes)


def test_full_government_history_does_not_fetch_another_price_file():
    calls = []
    def load(symbol, category, refresh):
        calls.append(category)
        return prices()
    selected, _ = load_kr_prices(load, "005930", "auto")
    assert selected.height == 270 and calls == ["govPriceCompany"]


def test_missing_government_file_uses_valid_krx_file():
    def load(symbol, category, refresh):
        if category == "govPriceCompany": raise FileNotFoundError("not cached")
        return prices()
    selected, notes = load_kr_prices(load, "005930", "local_only")
    assert selected.height == 270 and any("govPriceCompany" in n for n in notes)


def test_samsung_style_three_metric_case_explains_and_adds_dividend_without_filling_research(monkeypatch, tmp_path):
    from dartlab.core import dataLoader
    source = Source(title="annual filing", as_of=date(2026, 3, 10))
    financial = {key: Observation(value=value, evidence="Comparable complete annual filings", sources=[source])
                 for key, value in {"revenue_cagr": 1, "profit_cagr": -5, "debt_ratio": 35}.items()}
    assert analyze(AnalysisInput(observations=financial))["coverage"] == 15.83
    monkeypatch.setenv("GEMS_DARTLAB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data, "_financial_observations", lambda *_: (financial.copy(), "삼성전자", []))
    calls = []
    def load(symbol, category, refresh):
        calls.append((symbol, category, refresh))
        if category == "finance": return pl.DataFrame()
        if category == "report": return reports()
        if category == "govPriceCompany": return prices().tail(142)
        raise FileNotFoundError("KRX file not cached")
    monkeypatch.setattr(dataLoader, "loadData", load)
    response = TestClient(app).post("/api/company", json={"symbol": "005930", "market": "KR", "offline": True})
    assert response.status_code == 200
    company = AnalysisInput.model_validate(response.json())
    result = analyze(company)
    assert result["coverage"] == 19.17 and result["scored_count"] == 4
    assert result["score"] is None and result["collection_summary"]["research_count"] == 15
    assert all(call[2] == "local_only" for call in calls)
    assert "142" in company.collection_notes["trend"] and "220" in company.collection_notes["trend"]
    items = {item["id"]: item for group in result["groups"] for item in group["items"]}
    assert "142" in items["trend"]["reason"]
    assert "공시·IR" in items["brand"]["reason"]
    assert items["brand"]["score"] is None
    assert company.observations["dividend"].context["fiscal_year"] == 2025


def test_price_download_failure_does_not_discard_financials_or_dividend(monkeypatch, tmp_path):
    from dartlab.core import dataLoader
    monkeypatch.setenv("GEMS_DARTLAB_DATA_DIR", str(tmp_path))
    obs = Observation(value=35, evidence="same quarter", sources=[Source(title="filing", as_of=date(2026, 3, 10))])
    monkeypatch.setattr(data, "_financial_observations", lambda *_: ({"debt_ratio": obs}, "삼성전자", []))
    def load(symbol, category, refresh):
        if category == "finance": return pl.DataFrame()
        if category == "report": return reports()
        raise RuntimeError("price download failed")
    monkeypatch.setattr(dataLoader, "loadData", load)
    company = data.load_company("005930", "KR", True)
    assert {"dividend", "debt_ratio"}.issubset(company.observations) and company.current_price is None
    assert "price download failed" in company.collection_notes["trend"]


def test_collection_notes_validate_known_criteria_and_never_count_as_evidence():
    with pytest.raises(ValueError):
        AnalysisInput(collection_notes={"unknown": "missing"})
    result = analyze(AnalysisInput(collection_notes={"trend": "history missing"}))
    assert result["coverage"] == 0
    assert result["groups"][3]["items"][-1]["reason"] == "history missing"
