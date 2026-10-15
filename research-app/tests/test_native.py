import re

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("dartlab")


def test_native_ui_assets_and_api_namespaces_keep_upstream_contracts(tmp_path, monkeypatch):
    monkeypatch.setenv("DARTLAB_HOME", str(tmp_path / "dartlab"))
    monkeypatch.setenv("GEMS_DARTLAB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GEMS_STATE_DIR", str(tmp_path / "gems"))
    from gems_research.native import create_app
    from dartlab.server._ui_path import resolveUiBuildDir

    app = create_app()
    original = (resolveUiBuildDir() / "index.html").read_text(encoding="utf-8")
    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "gems-launcher" not in original  # upstream package not edited
        assert '/_gems-extension/bridge.js' in root.text
        asset = re.search(r'href="(/_app/[^\"]+\.js)"', original).group(1)
        response = client.get(asset)
        assert response.status_code == 200
        assert response.content == (resolveUiBuildDir() / asset.lstrip("/")).read_bytes()
        assert client.get("/terminal/005930").text == root.text
        assert client.get("/analysis/AAPL/viewer").text == root.text
        assert client.get("/_gems-extension/bridge.js").status_code == 200
        assert 'href="static/style.css"' in client.get("/gems/").text
        assert client.get("/gems/static/app.js").status_code == 200
        assert client.get("/gems/static/forecast.js").status_code == 200
        assert 'gems-forecast-launcher' in client.get("/_gems-extension/bridge.js").text
        assert len(client.get("/gems/api/rubric").json()["criteria"]) == 21
        demo = client.get("/gems/api/demo").json()
        assert client.post("/gems/api/analyze", json=demo).json()["result"]["coverage"] == 100
        assert client.post("/gems/api/review", json=demo).status_code == 200
        outlook = client.post("/gems/api/forecast", json={"symbol": "DEMO", "demo": True}).json()
        assert outlook["horizon"] == 20 and len(outlook["future"]) == 20
        assert client.get("/openapi.json").json()["info"]["title"] == "DartLab"
        assert client.get("/", headers={"host": "unexpected.example"}).status_code == 400
