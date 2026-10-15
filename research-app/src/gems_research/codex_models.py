"""Account-aware model selection for DartLab 0.12.0's Codex transport.

No Codex credentials or global configuration files are read or changed.
The authenticated app-server's account type and catalog validate any app-local
model choice saved explicitly by the user.
The adapter retains every upstream tool, sandbox and approval parameter.
"""
from __future__ import annotations

import logging
import json
import re
import uuid
from typing import Any

from .storage import database_path

logger = logging.getLogger(__name__)


def saved_model() -> str | None:
    path = database_path().with_name("codex-model.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("model")
    except FileNotFoundError:
        return None
    except (ValueError, AttributeError) as exc:
        raise RuntimeError("앱의 Codex 모델 설정을 읽지 못했습니다.") from exc
    return value if isinstance(value, str) and value.strip() else None


def save_model(model: str) -> None:
    path = database_path().with_name("codex-model.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps({"model": model}), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def rejected_model(detail: str) -> str | None:
    match = re.search(r"The '([^'\r\n]{1,200})' model is not supported when using Codex with a ChatGPT account", detail)
    return match.group(1) if match else None


class AccountModelChannel:
    def __init__(self, channel):
        self.channel = channel
        self.configured_model: str | None = None
        self.configured_provider: str | None = None
        self.threads: dict[str, dict] = {}

    def __getattr__(self, name):
        return getattr(self.channel, name)

    def catalog(self) -> dict[str, dict]:
        """Read every visible model page without opening a thread or AI turn."""
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
                return models
            if not isinstance(cursor, str) or cursor in seen:
                raise RuntimeError("Codex 모델 목록을 완전히 확인하지 못했습니다. 다시 연결하세요.")
            seen.add(cursor)
        raise RuntimeError("Codex 모델 목록 조회 한도를 초과했습니다. CLI를 확인하세요.")

    def _chatgpt_model(self, explicit: str | None, provider: str | None = None) -> dict | None:
        if (provider or self.configured_provider) not in {None, "openai"}:
            return None
        account = self.channel.request("account/read", {"refreshToken": False}, timeout=15).get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            return None  # API keys and custom providers retain their original policy.
        models = self.catalog()
        override = saved_model()
        preferred = explicit or override or self.configured_model
        if preferred in models:
            return {**models[preferred], "selectedModel": preferred, "policyModel": override}
        if explicit or override:
            raise RuntimeError("선택한 모델이 현재 ChatGPT 계정의 Codex 모델 목록에 없습니다. 지원 모델을 선택하세요.")
        defaults = [(name, model) for name, model in models.items() if model.get("isDefault") is True]
        if len(defaults) != 1:
            raise RuntimeError("계정의 Codex 기본 모델을 확인하지 못했습니다. Codex에서 /model을 확인하고 다시 연결하세요.")
        name, model = defaults[0]
        logger.info("DartLab Codex: inherited model unavailable; using account default %s", name)
        return {**model, "selectedModel": name, "policyModel": override}

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
            # Existing/resumed threads must also adopt a newly selected model.
            if selected.get("policyModel") != saved_model():
                selected = self._chatgpt_model(None)
                if selected is None:
                    raise RuntimeError("Codex 로그인 유형이 변경되었습니다. 새 대화를 시작하세요.")
                self.threads[params["threadId"]] = selected
            params = {**params, "model": selected["selectedModel"]}
            supported = {e.get("reasoningEffort") for e in selected.get("supportedReasoningEfforts") or [] if isinstance(e, dict)}
            if supported and params.get("effort") not in supported:
                default = selected.get("defaultReasoningEffort")
                if default in supported:
                    params["effort"] = default
                else:
                    params.pop("effort", None)
        return self.channel.request(method, params, timeout=timeout)


def inspect_connection() -> dict:
    """Inspect CLI metadata only; never submit prompts or expose credentials."""
    from pathlib import Path
    from dartlab.ai.runtime.discovery import discoverExecutable
    from dartlab.ai.runtime.drivers.base import runtimeLaunchArgv
    from dartlab.ai.runtime.contracts import ProcessSpec
    from dartlab.ai.runtime.processSupervisor import ProcessSupervisor, JsonRpcChannel
    from dartlab.ai.runtime.registry import loadRuntimeRegistry

    descriptor = loadRuntimeRegistry()["codex"]
    executable = discoverExecutable(descriptor)
    if not executable:
        raise RuntimeError("Codex CLI를 찾지 못했습니다. Runtime Center에서 설치하세요.")
    supervisor = ProcessSupervisor(ProcessSpec((*runtimeLaunchArgv(descriptor, executable),
                                               "-c", "features.hooks=false", "-c", "features.plugins=false"), Path.cwd()))
    try:
        supervisor.start()
        channel = AccountModelChannel(JsonRpcChannel(supervisor))
        channel.request("initialize", {"clientInfo": {"name": "gems-research", "version": "1"},
                                       "capabilities": {"experimentalApi": True}}, timeout=15)
        channel.notify("initialized", {})
        channel.request("config/read", {"cwd": str(Path.cwd())}, timeout=15)
        account = channel.request("account/read", {"refreshToken": False}, timeout=15).get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            raise RuntimeError("ChatGPT 로그인을 확인하지 못했습니다. 이 복구 기능은 ChatGPT 로그인 전용입니다.")
        if channel.configured_provider not in {None, "openai"}:
            raise RuntimeError("사용자 지정 공급자 설정이 있습니다. 해당 연결의 모델 설정을 확인하세요.")
        models = channel.catalog()
        return {"account_type": "chatgpt", "configured_model": channel.configured_model,
                "saved_model": saved_model(),
                "models": [{"model": name, "label": item.get("displayName") or name,
                            "is_default": item.get("isDefault") is True} for name, item in models.items()]}
    finally:
        supervisor.stop()


def recover_connection(model: str) -> dict:
    from dartlab.ai.runtime import getRuntimeEngine
    from dartlab.ai.runtime.readiness import _DELIVERY_CACHE

    info = inspect_connection()  # Revalidate at apply time, not just when the dialog opened.
    if model not in {item["model"] for item in info["models"]}:
        raise ValueError("현재 계정의 모델 목록에서 선택하세요.")
    engine = getRuntimeEngine()
    delivery = engine.sessionStore.getDelivery("codex") or {}
    rejected = rejected_model(delivery.get("detail", ""))
    if rejected == model:
        raise ValueError("서버가 미지원으로 거절한 모델입니다. 다른 모델을 선택하세요.")
    save_model(model)
    reset = delivery.get("state") == "blocked" and bool(rejected)
    if reset:
        # Retain the original failure detail; unknown is not evidence of delivery.
        engine.sessionStore.recordDelivery("codex", "unknown", delivery.get("detail", ""))
        _DELIVERY_CACHE.clear("codex")
    return {"model": model, "model_error_reset": reset,
            "other_error_blocked": delivery.get("state") == "blocked" and not reset,
            "delivery_verified": False}


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
