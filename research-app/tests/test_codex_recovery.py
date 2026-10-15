from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gems_research import codex_models
from gems_research.codex_api import router

ERROR = '{"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The \'gpt-6.1-sol\' model is not supported when using Codex with a ChatGPT account."}}'
CATALOG = {"account_type": "chatgpt", "configured_model": "gpt-6.1-sol", "saved_model": None,
           "models": [{"model": "gpt-6.1-sol", "label": "Old", "is_default": False},
                      {"model": "account-default", "label": "Default", "is_default": True}]}


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    pytest.importorskip("dartlab")
    import dartlab.ai.runtime as runtime
    from dartlab.ai.runtime.sessionStore import SessionStore
    from dartlab.ai.runtime.readiness import _DELIVERY_CACHE

    monkeypatch.setenv("GEMS_STATE_DIR", str(tmp_path / "gems"))
    store = SessionStore(tmp_path / "runtime.sqlite3")
    store.recordDelivery("codex", "blocked", ERROR)
    store.recordDelivery("claude", "blocked", "quota")
    monkeypatch.setattr(runtime, "getRuntimeEngine", lambda: SimpleNamespace(sessionStore=store))
    monkeypatch.setattr(codex_models, "inspect_connection", lambda: deepcopy(CATALOG))
    _DELIVERY_CACHE.clear()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield store, client
    _DELIVERY_CACHE.clear()


def test_check_retains_failure_and_returns_only_model_metadata(recovery):
    store, client = recovery
    response = client.post("/_gems-extension/codex/check")
    assert response.status_code == 200
    assert response.json()["rejected_model"] == "gpt-6.1-sol"
    assert response.json()["delivery_state"] == "blocked"
    assert store.getDelivery("codex")["state"] == "blocked"
    assert codex_models.saved_model() is None


def test_model_recovery_resets_only_exact_codex_model_failure_and_invalidates_cache(recovery):
    from dartlab.ai.runtime.readiness import _deliveryRecord
    store, client = recovery
    assert _deliveryRecord(store, "codex")["state"] == "blocked"
    response = client.post("/_gems-extension/codex/recover", json={"model": "account-default"})
    assert response.status_code == 200
    assert response.json() == {"model": "account-default", "model_error_reset": True,
                               "other_error_blocked": False, "delivery_verified": False}
    assert _deliveryRecord(store, "codex")["state"] == "unknown"
    assert store.getDelivery("codex")["detail"] == ERROR
    assert store.getDelivery("claude")["state"] == "blocked"
    assert codex_models.saved_model() == "account-default"


@pytest.mark.parametrize("model", ["gpt-6.1-sol", "made-up"])
def test_rejected_or_missing_model_cannot_be_applied(recovery, model):
    store, client = recovery
    assert client.post("/_gems-extension/codex/recover", json={"model": model}).status_code == 400
    assert store.getDelivery("codex")["state"] == "blocked"
    assert codex_models.saved_model() is None


def test_unrelated_failure_is_never_cleared(recovery):
    store, client = recovery
    store.recordDelivery("codex", "blocked", "Usage limit reached")
    response = client.post("/_gems-extension/codex/recover", json={"model": "account-default"})
    assert response.json()["other_error_blocked"] is True
    assert store.getDelivery("codex")["state"] == "blocked"


def test_connection_failure_does_not_change_settings_or_failures(recovery, monkeypatch):
    store, client = recovery
    def fail():
        raise RuntimeError("private transport detail")
    monkeypatch.setattr(codex_models, "inspect_connection", fail)
    response = client.post("/_gems-extension/codex/recover", json={"model": "account-default"})
    assert response.status_code == 400
    assert "private" not in response.text
    assert codex_models.saved_model() is None
    assert store.getDelivery("codex")["state"] == "blocked"


def test_foreign_origin_cannot_launch_check_or_apply(recovery):
    _, client = recovery
    for path in ("check", "recover"):
        response = client.post("/_gems-extension/codex/" + path, json={"model": "account-default"},
                               headers={"Origin": "https://unrelated.example"})
        assert response.status_code == 403


def test_inspection_closes_transport_without_opening_thread_or_turn(monkeypatch, tmp_path):
    pytest.importorskip("dartlab")
    from dartlab.ai.runtime import discovery, processSupervisor
    from test_codex_models import FakeChannel

    monkeypatch.setenv("GEMS_STATE_DIR", str(tmp_path))
    transports = []
    class Supervisor:
        def __init__(self, spec):
            self.stopped = False
            transports.append(self)
        def start(self):
            pass
        def stop(self):
            self.stopped = True

    channels = []
    def factory(supervisor):
        channel = FakeChannel()
        channels.append(channel)
        return channel

    monkeypatch.setattr(discovery, "discoverExecutable", lambda descriptor: str(tmp_path / "codex"))
    from dartlab.ai.runtime.drivers import base
    monkeypatch.setattr(base, "runtimeLaunchArgv", lambda *args: ("codex", "app-server"))
    monkeypatch.setattr(processSupervisor, "ProcessSupervisor", Supervisor)
    monkeypatch.setattr(processSupervisor, "JsonRpcChannel", factory)
    info = codex_models.inspect_connection()
    assert info["account_type"] == "chatgpt"
    assert info["models"][0]["model"] == "account-default"
    assert transports[0].stopped
    assert not any(method.startswith(("thread/", "turn/")) for method, _ in channels[0].calls)
