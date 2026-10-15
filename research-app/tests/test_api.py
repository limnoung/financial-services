from fastapi.testclient import TestClient

from gems_research.data import demo_input
from gems_research.models import AnalysisInput
from gems_research.reports import markdown_report
from gems_research.scoring import analyze
from gems_research.server import app

client = TestClient(app)


def test_rubric_and_local_ui():
    response = client.get("/api/rubric")
    assert response.status_code == 200
    assert len(response.json()["criteria"]) == 21
    assert sum(g["weight"] for g in response.json()["groups"]) == 100
    assert "투자 매력도 검토" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_score_and_gemini_handoff_do_not_claim_ai_execution():
    data = client.get("/api/demo").json()
    result = client.post("/api/analyze", json=data)
    assert result.status_code == 200
    assert result.json()["result"]["coverage"] == 100
    assert result.json()["input"]["symbol"] == "DEMO"
    assert "가상 예시 데이터" in result.json()["report"]
    assert "임의로 수정하지" in result.json()["gems_prompt"]


def test_invalid_payload_does_not_overwrite_history(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMS_STATE_DIR", str(tmp_path))
    response = client.post("/api/save", json={"observations": {"bad": {"value": 1}}})
    assert response.status_code == 422
    assert client.get("/api/history").json() == []


def test_immutable_snapshots_roundtrip_and_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMS_STATE_DIR", str(tmp_path))
    data = demo_input().model_dump(mode="json")
    first = client.post("/api/save", json=data).json()["id"]
    data["observations"]["brand"]["score"] = 1
    second = client.post("/api/save", json=data).json()["id"]
    assert first != second
    assert len(client.get("/api/history").json()) == 2
    assert client.get("/api/history/" + first).json()["payload"]["observations"]["brand"]["score"] == 3
    assert client.get("/api/history/" + second).json()["payload"]["observations"]["brand"]["score"] == 1
    assert client.get("/api/history/missing").status_code == 404


def test_target_upside_requires_independent_basis():
    data = AnalysisInput(current_price=100, target_price=120)
    assert analyze(data)["upside"] is None
    data.target_basis = "별도 가치평가 가정"
    assert analyze(data)["upside"] is None
    data.price_date = data.as_of
    assert analyze(data)["upside"] == 20


def test_future_price_date_is_rejected():
    assert client.post("/api/analyze", json={"as_of": "2026-01-01", "price_date": "2026-01-02"}).status_code == 422


def test_report_displays_incomplete_data_and_does_not_invent_risks():
    data = AnalysisInput()
    report = markdown_report(data, analyze(data))
    assert "미확정" in report
    assert "미평가" in report
    assert "핵심 리스크와 투자 논리를 철회할 조건을 입력" in report


def test_remote_host_is_not_a_public_service():
    assert client.get("/", headers={"host": "unexpected.example"}).status_code == 400
