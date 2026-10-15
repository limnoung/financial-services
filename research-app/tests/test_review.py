from datetime import date

from fastapi.testclient import TestClient

from gems_research.data import demo_input
from gems_research.models import AnalysisInput, Observation, Peer, Source
from gems_research.review import financial_review
from gems_research.server import app


def checks(data):
    return {item["label"]: item for item in financial_review(data)["checks"]}


def test_missing_inputs_do_not_pass_review():
    result = checks(AnalysisInput())
    assert result["자료 기준일"]["status"] == "missing"
    assert result["경쟁사 근거"]["status"] == "missing"
    assert result["가치평가와 점수 분리"]["status"] == "missing"
    assert result["원본 모델 검산"]["status"] == "missing"


def test_future_sources_and_inconsistent_growth_periods_are_flagged():
    data = AnalysisInput(as_of=date(2026, 1, 1), observations={
        "revenue_cagr": Observation(value=10, evidence="매출", sources=[Source(title="미래 공시", as_of=date(2027, 1, 1))], context={"start_year": "2022", "end_year": "2025"}),
        "profit_cagr": Observation(value=10, context={"start_year": "2021", "end_year": "2024"}),
    })
    result = checks(data)
    assert result["자료 기준일"]["status"] == "warning"
    assert result["성장률 비교 기간"]["status"] == "warning"


def test_peer_text_is_not_treated_as_verified_comparability():
    data = demo_input()
    data.peers = [Peer(name="A", metrics="P/E 10", source="IR"), Peer(name="B", metrics="P/E 20", source="IR")]
    result = checks(data)
    assert result["경쟁사 근거"]["status"] == "ready"
    assert "추가 확인" in result["경쟁사 근거"]["detail"]
    data.profile = "financial"
    assert checks(data)["업종별 기준"]["status"] == "warning"


def test_review_and_original_workflows_are_available_in_api_and_reports():
    client = TestClient(app)
    data = demo_input().model_dump(mode="json")
    reviewed = client.post("/api/review", json=data)
    assert reviewed.status_code == 200
    assert len(reviewed.json()["workflows"]) == 4
    assert "가상 예시 데이터" in reviewed.json()["prompt"]
    for flow in reviewed.json()["workflows"]:
        source = client.get("/api/workflows/" + flow["id"])
        assert source.status_code == 200
        assert "Source: https://github.com/limnoung/financial-services/blob/" in source.text
    assert client.get("/api/workflows/not-a-workflow").status_code == 404
    report = client.post("/api/analyze", json=data).json()
    assert "## 7 재무 검토" in report["report"]
    assert report["review"]["checks"][-1]["status"] == "missing"


def test_malformed_optional_period_metadata_does_not_crash_import():
    data = demo_input().model_dump(mode="json")
    data["observations"]["revenue_cagr"]["context"] = {"start_year": [2022], "end_year": {"year": 2025}}
    response = TestClient(app).post("/api/analyze", json=data)
    assert response.status_code == 200
    check = next(c for c in response.json()["review"]["checks"] if c["label"] == "성장률 비교 기간")
    assert check["status"] == "missing"
