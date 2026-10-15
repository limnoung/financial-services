from copy import deepcopy
from pathlib import Path

import pytest

from gems_research.codex_models import AccountModelChannel, install_codex_model_bridge, save_model


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMS_STATE_DIR", str(tmp_path / "gems"))


DEFAULT = dict(model="account-default", isDefault=True, defaultReasoningEffort="medium",
               supportedReasoningEfforts=[dict(reasoningEffort="low"), dict(reasoningEffort="medium")])


class FakeChannel:
    def __init__(self, supervisor=None, *, account="chatgpt", models=None):
        self.account = account
        self.models = [deepcopy(DEFAULT)] if models is None else models
        self.calls = []
        self.config = {"model": "gpt-6.1-sol", "mcp_servers": {"example": {"enabled": True}}}

    def request(self, method, params, *, timeout=30):
        self.calls.append((method, deepcopy(params)))
        if method == "initialize":
            return {}
        if method == "config/read":
            return {"config": deepcopy(self.config)}
        if method == "account/read":
            return {"account": {"type": self.account}}
        if method == "model/list":
            return {"data": self.models}
        if method in {"thread/start", "thread/resume"}:
            return {"thread": {"id": "native-thread"}}
        if method == "turn/start":
            return {"turn": {"id": "turn"}}
        raise AssertionError(method)

    def notify(self, method, params):
        self.calls.append((method, deepcopy(params)))

    def nextMessage(self, *, timeout):
        return {"method": "turn/completed", "params": {"threadId": "native-thread", "turn": {"id": "turn", "status": "completed"}}}


def opened_channel(**kwargs):
    raw = FakeChannel(**kwargs)
    channel = AccountModelChannel(raw)
    channel.request("config/read", {"cwd": "workspace"})
    channel.request("thread/start", {"approvalPolicy": "never", "sandbox": "read-only"})
    return channel, raw


def test_unsupported_inherited_model_uses_native_account_default_without_changing_config():
    channel, raw = opened_channel()
    assert raw.calls[-1] == ("thread/start", {"approvalPolicy": "never", "sandbox": "read-only", "model": "account-default"})
    assert raw.config["model"] == "gpt-6.1-sol"
    original = {"threadId": "native-thread", "effort": "high", "approvalPolicy": "never",
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False}, "input": [{"type": "text", "text": "분석"}]}
    channel.request("turn/start", original)
    assert raw.calls[-1][1] == {**original, "model": "account-default", "effort": "medium"}
    assert original["effort"] == "high"
    assert "model" not in original


@pytest.mark.parametrize("account", ["apiKey", "custom-provider", None])
def test_api_key_or_unknown_auth_keeps_original_model_policy(account):
    channel, raw = opened_channel(account=account)
    assert "model" not in raw.calls[-1][1]
    assert not any(method == "model/list" for method, _ in raw.calls)
    turn = {"threadId": "native-thread", "effort": "high"}
    channel.request("turn/start", turn)
    assert raw.calls[-1][1] == turn


def test_supported_configured_model_is_kept_instead_of_default():
    preferred = dict(model="gpt-6.1-sol", isDefault=False)
    channel, raw = opened_channel(models=[DEFAULT, preferred])
    assert raw.calls[-1][1]["model"] == "gpt-6.1-sol"


def test_app_choice_overrides_inherited_model_even_if_catalog_still_advertises_it():
    save_model("account-default")
    channel, raw = opened_channel(models=[DEFAULT, dict(model="gpt-6.1-sol")])
    assert raw.calls[-1][1]["model"] == "account-default"
    assert raw.config["model"] == "gpt-6.1-sol"


def test_existing_thread_adopts_new_choice_on_next_turn():
    channel, raw = opened_channel(models=[DEFAULT, dict(model="gpt-6.1-sol")])
    assert raw.calls[-1][1]["model"] == "gpt-6.1-sol"
    save_model("account-default")
    channel.request("turn/start", {"threadId": "native-thread", "effort": "high"})
    assert raw.calls[-1][1]["model"] == "account-default"
    assert raw.calls[-1][1]["effort"] == "medium"


def test_saved_choice_never_changes_api_key_policy():
    save_model("account-default")
    _, raw = opened_channel(account="apiKey")
    assert "model" not in raw.calls[-1][1]


def test_removed_saved_model_does_not_silently_choose_another():
    save_model("removed")
    with pytest.raises(RuntimeError, match="지원 모델"):
        opened_channel()


def test_custom_provider_is_preserved_even_with_a_saved_chatgpt_login():
    raw = FakeChannel(account="chatgpt")
    raw.config["model_provider"] = "custom-api"
    channel = AccountModelChannel(raw)
    channel.request("config/read", {})
    channel.request("thread/start", {})
    assert raw.calls[-1] == ("thread/start", {})
    assert not any(method in {"account/read", "model/list"} for method, _ in raw.calls)


def test_explicit_unavailable_model_is_not_silently_replaced():
    raw = FakeChannel()
    channel = AccountModelChannel(raw)
    with pytest.raises(RuntimeError, match="지원 모델"):
        channel.request("thread/start", {"model": "explicit-not-in-catalog"})
    assert not any(method == "thread/start" for method, _ in raw.calls)


@pytest.mark.parametrize("models", [[], [dict(model="unconfirmed")], [dict(model="hidden-default", hidden=True, isDefault=True)], [DEFAULT, dict(model="second-default", isDefault=True)]])
def test_empty_hidden_or_ambiguous_catalog_never_guesses_a_model(models):
    with pytest.raises(RuntimeError, match="기본 모델"):
        opened_channel(models=models)


def test_catalog_pagination_uses_default_on_later_page():
    raw = FakeChannel()
    request = raw.request

    def paged(method, params, **kwargs):
        if method == "model/list":
            return {"data": [DEFAULT]} if params.get("cursor") == "page2" else {"data": [dict(model="other")], "nextCursor": "page2"}
        return request(method, params, **kwargs)

    raw.request = paged
    channel = AccountModelChannel(raw)
    channel.request("thread/resume", {"threadId": "saved-thread"})
    assert raw.calls[-1][1]["model"] == "account-default"


def test_repeating_cursor_fails_instead_of_looping():
    raw = FakeChannel()
    request = raw.request
    raw.request = lambda method, params, **kwargs: {"data": [], "nextCursor": "same"} if method == "model/list" else request(method, params, **kwargs)
    with pytest.raises(RuntimeError, match="완전히 확인"):
        AccountModelChannel(raw).request("thread/start", {})


def test_real_dartlab_driver_keeps_sandbox_tools_and_stream_protocol(monkeypatch, tmp_path):
    pytest.importorskip("dartlab")
    from dartlab.ai.runtime.drivers import codexAppServer
    from dartlab.ai.runtime.registry import loadRuntimeRegistry

    class Supervisor:
        def __init__(self, spec):
            self.spec = spec

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(codexAppServer, "ProcessSupervisor", Supervisor)
    monkeypatch.setattr(codexAppServer, "runtimeLaunchArgv", lambda *args: ("codex", "app-server"))
    monkeypatch.setattr(codexAppServer, "JsonRpcChannel", FakeChannel)
    install_codex_model_bridge()
    factory = codexAppServer.JsonRpcChannel
    install_codex_model_bridge()
    assert codexAppServer.JsonRpcChannel is factory
    driver = codexAppServer.CodexAppServerDriver()
    handle = driver.open(loadRuntimeRegistry()["codex"], "codex", "session", tmp_path, instructions="analysis rules")
    assert isinstance(handle.channel, AccountModelChannel)
    start = next(params for method, params in handle.channel.channel.calls if method == "thread/start")
    assert start["model"] == "account-default"
    assert start["approvalPolicy"] == "never"
    assert start["sandbox"] == "read-only"
    assert start["developerInstructions"] == "analysis rules"
    assert start["dynamicTools"]
    assert start["config"]["features"]["shell_tool"] is False
    assert start["config"]["mcp_servers"] == {"example": {"enabled": False}}
    events = list(driver.streamTurn(handle, "기업 분석", instructions="analysis rules"))
    assert events
    turn = next(params for method, params in handle.channel.channel.calls if method == "turn/start")
    assert turn["model"] == "account-default"
    assert turn["effort"] == "medium"
    assert turn["approvalPolicy"] == "never"
    assert turn["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    driver.close(handle)
