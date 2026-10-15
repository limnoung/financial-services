"""Account-aware model selection for DartLab 0.12.0's Codex transport.

No credentials or user configuration files are read or changed. Only the
authenticated app-server's own account type and model catalog are consulted.
The adapter retains every upstream tool, sandbox and approval parameter.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AccountModelChannel:
    def __init__(self, channel):
        self.channel = channel
        self.configured_model: str | None = None
        self.configured_provider: str | None = None
        self.threads: dict[str, dict] = {}

    def __getattr__(self, name):
        return getattr(self.channel, name)

    def _chatgpt_model(self, explicit: str | None, provider: str | None = None) -> dict | None:
        if (provider or self.configured_provider) not in {None, "openai"}:
            return None
        account = self.channel.request("account/read", {"refreshToken": False}, timeout=15).get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            return None  # API keys and custom providers retain their original policy.
        models = {}
        cursor = None
        seen = set()
        for _ in range(10):
            params: dict[str, Any] = {"includeHidden": False}
            if cursor:
                params["cursor"] = cursor
            page = self.channel.request("model/list", params, timeout=20)
            for model in page.get("data") or []:
                if not isinstance(model, dict) or model.get("hidden") is True:
                    continue
                name = model.get("model") or model.get("id")
                if isinstance(name, str) and name.strip():
                    models[name] = model
            cursor = page.get("nextCursor")
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in seen:
                raise RuntimeError("Codex 모델 목록을 완전히 확인하지 못했습니다. 다시 연결하세요.")
            seen.add(cursor)
        else:
            raise RuntimeError("Codex 모델 목록 조회 한도를 초과했습니다. CLI를 확인하세요.")
        preferred = explicit or self.configured_model
        if preferred in models:
            return {**models[preferred], "selectedModel": preferred}
        if explicit:
            raise RuntimeError("선택한 모델이 현재 ChatGPT 계정의 Codex 모델 목록에 없습니다. 지원 모델을 선택하세요.")
        defaults = [(name, model) for name, model in models.items() if model.get("isDefault") is True]
        if len(defaults) != 1:
            raise RuntimeError("계정의 Codex 기본 모델을 확인하지 못했습니다. Codex에서 /model을 확인하고 다시 연결하세요.")
        name, model = defaults[0]
        logger.info("DartLab Codex: inherited model unavailable; using account default %s", name)
        return {**model, "selectedModel": name}

    def request(self, method: str, params: dict, *, timeout: float = 30):
        if method == "config/read":
            result = self.channel.request(method, params, timeout=timeout)
            model = (result.get("config") or {}).get("model")
            self.configured_model = model if isinstance(model, str) else None
            provider = (result.get("config") or {}).get("model_provider")
            self.configured_provider = provider if isinstance(provider, str) else None
            return result
        if method in {"thread/start", "thread/resume"}:
            selected = self._chatgpt_model(params.get("model"), params.get("modelProvider"))
            payload = {**params, "model": selected["selectedModel"]} if selected else params
            result = self.channel.request(method, payload, timeout=timeout)
            thread = result.get("thread") or {}
            thread_id = thread.get("id") or result.get("threadId") or params.get("threadId")
            if selected and isinstance(thread_id, str):
                self.threads[thread_id] = selected
            return result
        if method == "turn/start" and params.get("threadId") in self.threads:
            selected = self.threads[params["threadId"]]
            params = {**params, "model": selected["selectedModel"]}
            supported = {e.get("reasoningEffort") for e in selected.get("supportedReasoningEfforts") or [] if isinstance(e, dict)}
            if supported and params.get("effort") not in supported:
                default = selected.get("defaultReasoningEffort")
                if default in supported:
                    params["effort"] = default
                else:
                    params.pop("effort", None)
        return self.channel.request(method, params, timeout=timeout)


def install_codex_model_bridge() -> None:
    """Augment the pinned driver's transport factory once for this process only."""
    from dartlab.ai.runtime.drivers import codexAppServer

    original = codexAppServer.JsonRpcChannel
    if getattr(original, "_gems_account_models", False):
        return

    def channel_factory(supervisor):
        return AccountModelChannel(original(supervisor))

    channel_factory._gems_account_models = True
    codexAppServer.JsonRpcChannel = channel_factory
