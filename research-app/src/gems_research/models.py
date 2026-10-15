from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def today_kst() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


class Source(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(default="", max_length=2000)
    as_of: date
    kind: Literal["fact", "estimate", "assumption"] = "fact"

    @field_validator("url")
    @classmethod
    def safe_link(cls, value: str) -> str:
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("출처 URL은 http 또는 https 주소여야 합니다.")
        return value

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("출처명을 입력하세요.")
        return value.strip()


class Observation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    value: float | str | None = None
    score: int | None = Field(default=None, ge=1, le=5, strict=True)
    evidence: str = Field(default="", max_length=6000)
    sources: list[Source] = Field(default_factory=list, max_length=12)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value", mode="before")
    @classmethod
    def finite_value(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("숫자에 true/false를 사용할 수 없습니다.")
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError("유한한 숫자를 입력하세요.")
        return value


class Peer(BaseModel):
    name: str = Field(max_length=100)
    metrics: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=2000)


class AnalysisInput(BaseModel):
    symbol: str = Field(default="005930", pattern=r"^[A-Za-z0-9.^_-]{1,20}$")
    name: str = Field(default="", max_length=120)
    market: Literal["KR", "US"] = "KR"
    profile: Literal["general", "financial", "reit", "preprofit"] = "general"
    as_of: date = Field(default_factory=today_kst)
    observations: dict[str, Observation] = Field(default_factory=dict, max_length=40)
    thesis: list[str] = Field(default_factory=list, max_length=3)
    risks: list[str] = Field(default_factory=list, max_length=3)
    peers: list[Peer] = Field(default_factory=list, max_length=3)
    current_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    target_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    price_date: date | None = None
    target_basis: str = Field(default="", max_length=3000)
    notes: list[str] = Field(default_factory=list, max_length=30)
    collection_notes: dict[str, str] = Field(default_factory=dict, max_length=40)
    demo: bool = False

    @model_validator(mode="after")
    def known_observations(self):
        from .rubric import BY_ID
        unknown = (set(self.observations) | set(self.collection_notes)) - BY_ID.keys()
        if unknown:
            raise ValueError("정의되지 않은 항목: " + ", ".join(sorted(unknown)))
        if self.price_date and self.price_date > self.as_of:
            raise ValueError("가격 기준일은 분석 기준일을 넘을 수 없습니다.")
        return self


class LoadInput(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9.^_-]{1,20}$")
    market: Literal["KR", "US"] = "KR"
    offline: bool = False


class ForecastInput(LoadInput):
    horizon: Literal[5, 20, 60] = 20
    lookback: Literal[63, 126, 252] = 126
    method: Literal["ar1", "drift"] = "ar1"
    as_of: date = Field(default_factory=today_kst)
    demo: bool = False

    @field_validator("as_of")
    @classmethod
    def no_future_cutoff(cls, value: date) -> date:
        if value > today_kst():
            raise ValueError("예측 기준일은 오늘을 넘을 수 없습니다.")
        return value
