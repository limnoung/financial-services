"""Local, explicit Codex metadata checks and model recovery."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import __version__
from . import codex_models

router = APIRouter(prefix="/_gems-extension")


class ModelSelection(BaseModel):
    model: str = Field(min_length=1, max_length=200)


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="이 화면에서 직접 실행하세요.")


@router.post("/codex/check")
def check(request: Request):
    same_origin(request)
    try:
        from dartlab.ai.runtime import getRuntimeEngine
        info = codex_models.inspect_connection()
        delivery = getRuntimeEngine().sessionStore.getDelivery("codex") or {}
        return {**info, "app_version": __version__, "delivery_state": delivery.get("state", "unknown"),
                "rejected_model": codex_models.rejected_model(delivery.get("detail", ""))}
    except (OSError, RuntimeError, TimeoutError, ValueError):
        raise HTTPException(status_code=400, detail="Codex 계정·모델 목록을 확인하지 못했습니다. Runtime Center의 설치·로그인 상태와 Codex CLI의 /model을 확인하세요.") from None


@router.post("/codex/recover")
def recover(request: Request, selection: ModelSelection):
    same_origin(request)
    try:
        return codex_models.recover_connection(selection.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except (OSError, RuntimeError, TimeoutError):
        raise HTTPException(status_code=400, detail="모델 연결을 적용하지 못했습니다. Codex CLI의 로그인 상태와 /model을 확인하고 다시 시도하세요.") from None
