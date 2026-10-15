from datetime import date

import pytest
from pydantic import ValidationError

from gems_research.data import cagr, demo_input
from gems_research.models import AnalysisInput, Observation, Source
from gems_research.rubric import BY_ID, CRITERIA, GROUPS
from gems_research.scoring import analyze, numeric_score

SOURCE = Source(title="테스트용 공시", as_of=date(2026, 1, 1))


def observation(value=None, score=None, **context):
    return Observation(value=value, score=score, evidence="비교 가능한 기간의 테스트 근거", sources=[SOURCE], context=context)


def all_at(level):
    numbers = {
        1: dict(market_share=0, margin_advantage=-6, revenue_cagr=-1, profit_cagr=-1, peg=2,
                forward_pe_ratio=1.3, dividend=0, net_buyback=-1, relative_return=-26,
                high_distance=60, institution_change=-6, tam_growth=-1, debt_ratio=250),
        3: dict(market_share=18, margin_advantage=3, revenue_cagr=10, profit_cagr=15, peg=1.2,
                forward_pe_ratio=1, dividend=.5, net_buyback=.5, relative_return=0,
                high_distance=20, institution_change=0, tam_growth=7, debt_ratio=125),
        5: dict(market_share=40, margin_advantage=10, revenue_cagr=25, profit_cagr=30, peg=.7,
                forward_pe_ratio=.6, dividend=4, net_buyback=2, relative_return=25,
                high_distance=2, institution_change=5, tam_growth=20, debt_ratio=20),
    }[level]
    values = {}
    for item in CRITERIA:
        if item["kind"] == "qualitative":
            values[item["id"]] = observation(score=level)
        elif item["kind"] == "choice":
            values[item["id"]] = observation(value={1: "strong_down", 3: "mixed", 5: "strong_up"}[level])
        else:
            values[item["id"]] = observation(numbers[item["id"]])
    values["dividend"].context = dict(regular=True, growth_years=5, cut_recently=False)
    return AnalysisInput(observations=values, as_of=date(2026, 10, 15))


@pytest.mark.parametrize("level,expected", [(1, 0), (3, 50), (5, 100)])
def test_full_score_scale(level, expected):
    result = analyze(all_at(level))
    assert result["score"] == expected
    assert result["coverage"] == 100
    assert result["score_range"] == [expected, expected]


def test_equal_subweights_and_known_contribution():
    data = AnalysisInput(observations={"market_share": observation(50)})
    result = analyze(data)
    assert result["score"] is None
    assert result["coverage"] == 5
    assert result["provisional_score"] == 100
    assert result["score_range"] == [5, 100]
    assert result["band"] == "자료 보완 필요"


def test_missing_does_not_mean_bad():
    result = analyze(AnalysisInput())
    assert result["provisional_score"] is None
    assert result["score_range"] == [0, 100]
    assert result["groups"][0]["items"][0]["status"] == "missing"


@pytest.mark.parametrize("value,expected", [(.79, 5), (.8, 4), (1, 3), (1.5, 2), (2, 1)])
def test_peg_nonoverlapping_boundaries(value, expected):
    assert numeric_score(BY_ID["peg"], observation(value)) == expected


@pytest.mark.parametrize("value,expected", [(-5.01, 1), (-5, 2), (0, 3), (5, 4), (10, 5)])
def test_margin_boundaries(value, expected):
    assert numeric_score(BY_ID["margin_advantage"], observation(value)) == expected


@pytest.mark.parametrize("value,expected", [(0, 1), (5, 2), (10, 3), (25, 4), (40, 5)])
def test_market_share_boundaries(value, expected):
    assert numeric_score(BY_ID["market_share"], observation(value)) == expected


@pytest.mark.parametrize("key,value", [("market_share", 101), ("peg", -2), ("forward_pe_ratio", 0), ("revenue_cagr", -101)])
def test_invalid_numbers_do_not_produce_scores(key, value):
    result = analyze(AnalysisInput(observations={key: observation(value)}))
    assert result["scored_count"] == 0
    assert any(i["status"] == "invalid" for g in result["groups"] for i in g["items"])


def test_missing_evidence_and_future_source_block_score():
    data = all_at(3)
    data.observations["brand"].evidence = ""
    data.observations["switching"].sources = [Source(title="기준일 이후 공시", as_of=date(2027, 1, 1))]
    result = analyze(data)
    assert result["score"] is None
    assert result["scored_count"] == 19


def test_positive_values_do_not_override_distress():
    assert numeric_score(BY_ID["debt_ratio"], observation(10, interest_coverage=.5)) == 1
    assert numeric_score(BY_ID["debt_ratio"], observation(None, nonpositive_equity=True)) == 1
    assert numeric_score(BY_ID["profit_cagr"], observation(None, loss=True)) == 1


def test_dividend_cut_precedes_yield_and_growth():
    assert numeric_score(BY_ID["dividend"], observation(7, regular=True, growth_years=10, cut_recently=True)) == 2
    with pytest.raises(ValueError):
        numeric_score(BY_ID["dividend"], observation(7))


def test_special_sector_profile_is_explicitly_incomplete():
    data = all_at(3)
    data.profile = "financial"
    result = analyze(data)
    assert result["score"] is None
    assert result["scored_count"] == 18


def test_assumptions_are_allowed_but_preserved_as_assumptions():
    data = all_at(3)
    data.observations["market_share"].sources[0] = SOURCE.model_copy(update={"kind": "assumption"})
    result = analyze(data)
    assert result["groups"][0]["items"][0]["sources"][0]["kind"] == "assumption"
    assert result["evidence_basis"]["assumption"] == 5
    assert result["evidence_basis"]["fact"] == 95


def test_cagr_excludes_partial_year_and_requires_contiguous_years():
    assert cagr({"2022": 100, "2023": 110, "2024": 121, "2025": 133.1, "2026Q1": 40}) == pytest.approx(10)
    assert cagr({"2022": 100, "2024": 121, "2025": 133.1}) is None
    assert cagr({"2022": -100, "2023": 110, "2024": 121, "2025": 133.1}) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_nonfinite_or_boolean_observation_rejected(value):
    with pytest.raises(ValidationError):
        Observation(value=value)


def test_unknown_criterion_and_unsafe_source_url_rejected():
    with pytest.raises(ValidationError):
        AnalysisInput(observations={"invented_metric": observation(5)})
    with pytest.raises(ValidationError):
        Source(title="링크", as_of=date.today(), url="javascript:alert(1)")


def test_demo_is_always_marked_synthetic():
    data = demo_input()
    result = analyze(data)
    assert data.demo and result["demo"]
    assert result["coverage"] == 100
    assert all(s.kind == "assumption" for o in data.observations.values() for s in o.sources)
