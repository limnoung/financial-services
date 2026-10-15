"""Missing evidence stays missing. Uncovered weight is shown as a score interval."""
from __future__ import annotations

import math
from collections import Counter

from .models import AnalysisInput, Observation
from .rubric import CRITERIA, GROUPS, VERSION
from .collection import AUTOMATIC, missing_reason


def numeric_score(item: dict, obs: Observation) -> int:
    value = obs.value
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError as exc:
            raise ValueError("숫자를 입력하세요.") from exc
    if value is None:
        if item["id"] == "profit_cagr" and obs.context.get("loss") is True:
            return 1
        if item["id"] == "debt_ratio" and obs.context.get("nonpositive_equity") is True:
            return 1
        raise ValueError("숫자가 없습니다.")
    if not math.isfinite(value):
        raise ValueError("유한한 숫자가 필요합니다.")
    key = item["id"]
    if key in {"market_share", "high_distance", "dividend"} and not 0 <= value <= 100:
        raise ValueError("0~100% 범위가 필요합니다.")
    if key in {"revenue_cagr", "profit_cagr", "tam_growth"} and value < -100:
        raise ValueError("성장률은 -100% 미만일 수 없습니다.")
    if key in {"peg", "forward_pe_ratio"} and value <= 0:
        raise ValueError("양수의 유효한 추정치가 필요합니다. 적자·미확인은 미평가입니다.")
    if key == "net_buyback" and value > 100:
        raise ValueError("주식수 감소율이 100%를 초과할 수 없습니다.")
    rule = item.get("rule")
    if key == "profit_cagr" and obs.context.get("loss") is True:
        return 1
    if rule == "high":
        return 1 + sum(value >= cut for cut in item["cuts"])
    if rule == "low":
        return 5 - sum(value >= cut for cut in item["cuts"])
    if rule == "buyback":
        return 1 if value < 0 else 2 if value == 0 else 3 if value < 1 else 4 if value < 2 else 5
    if rule == "dividend":
        if value == 0:
            return 1
        if obs.context.get("cut_recently") is True:
            return 2
        if not isinstance(obs.context.get("regular"), bool):
            raise ValueError("정기 배당 여부(context.regular)를 확인하세요.")
        years = obs.context.get("growth_years")
        if value >= 3 and obs.context["regular"]:
            if not isinstance(years, (int, float)) or isinstance(years, bool) or years < 0:
                raise ValueError("배당 연속 증가 연수를 확인하세요.")
            if years >= 5:
                return 5
        return 4 if value >= 1 and obs.context["regular"] else 3
    if rule == "debt":
        if obs.context.get("nonpositive_equity") is True:
            return 1
        if "interest_coverage" in obs.context:
            coverage = obs.context["interest_coverage"]
            if isinstance(coverage, bool) or not isinstance(coverage, (float, int)) or not math.isfinite(coverage):
                raise ValueError("이자보상배율이 유효하지 않습니다.")
            if coverage < 1:
                return 1
        if value < 0:
            raise ValueError("음의 부채비율은 자본잠식 여부를 별도로 확인하세요.")
        return 5 - sum(value >= cut for cut in [50, 100, 150, 200])
    raise ValueError("평가 규칙을 찾을 수 없습니다.")


def assess(item: dict, obs: Observation | None, data: AnalysisInput) -> dict:
    result = dict(id=item["id"], label=item["label"], score=None, status="missing",
                  reason=data.collection_notes.get(item["id"]) or missing_reason(item["id"], data.market))
    if obs is None:
        return result
    result.update(evidence=obs.evidence, sources=[s.model_dump(mode="json") for s in obs.sources], value=obs.value)
    if item["id"] in {"peg", "forward_pe_ratio", "debt_ratio"} and data.profile != "general":
        return dict(result, status="profile_required", reason="이 업종은 검증된 대체 기준이 필요합니다. 일반 기준을 자동 적용하지 않습니다.")
    if not obs.sources or not obs.evidence.strip():
        return dict(result, status="needs_evidence", reason="출처·기준일과 근거를 입력하세요.")
    if any(source.as_of > data.as_of for source in obs.sources):
        return dict(result, status="invalid", reason="분석 기준일 이후 자료를 사용할 수 없습니다.")
    try:
        if item["kind"] == "qualitative":
            if obs.score is None:
                return dict(result, reason="근거에 따른 정성 점수 선택이 필요합니다.")
            score = obs.score
        elif item["kind"] == "choice":
            scores = dict(strong_down=1, death_cross=2, mixed=3, golden_cross=4, strong_up=5)
            if obs.value not in scores:
                raise ValueError("이동평균 상태를 선택하세요.")
            score = scores[obs.value]
        else:
            score = numeric_score(item, obs)
    except (ValueError, TypeError) as exc:
        return dict(result, status="invalid", reason=str(exc))
    return dict(result, score=score, status="scored", reason="입력 근거 기준 채점")


def analyze(data: AnalysisInput) -> dict:
    counts = Counter(item["group"] for item in CRITERIA)
    groups, all_items = [], []
    points, covered = 0.0, 0.0
    basis = dict(fact=0.0, estimate=0.0, assumption=0.0)
    for group_id, label, weight in GROUPS:
        items = [assess(item, data.observations.get(item["id"]), data) for item in CRITERIA if item["group"] == group_id]
        valid = [item for item in items if item["score"] is not None]
        unit_weight = weight / counts[group_id]
        contribution = sum(unit_weight * (item["score"] - 1) / 4 for item in valid)
        coverage = len(valid) * unit_weight
        for item in valid:
            kinds = {source["kind"] for source in item["sources"]}
            kind = "assumption" if "assumption" in kinds else "estimate" if "estimate" in kinds else "fact"
            basis[kind] += unit_weight
        points += contribution
        covered += coverage
        groups.append(dict(id=group_id, label=label, weight=weight, items=items,
                           coverage=round(len(valid) / len(items) * 100, 2),
                           average=round(sum(i["score"] for i in valid) / len(valid), 2) if valid else None,
                           contribution=round(contribution, 4)))
        all_items.extend(items)
    complete = all(item["score"] is not None for item in all_items)
    provisional = points / covered * 100 if covered else None
    score = round(points, 2) if complete else None
    band = None
    if complete:
        band = "매력도 높음" if score >= 80 else "검토 가치 있음" if score >= 60 else "중립적" if score >= 40 else "매력도 낮음"
    upside = None
    if data.current_price and data.price_date and data.target_price and data.target_basis.strip():
        upside = round((data.target_price / data.current_price - 1) * 100, 2)
    return dict(
        rubric_version=VERSION, symbol=data.symbol, name=data.name or data.symbol, market=data.market, profile=data.profile,
        as_of=data.as_of.isoformat(), demo=data.demo, status="complete" if complete else "incomplete",
        score=score, provisional_score=round(provisional, 2) if provisional is not None else None,
        coverage=round(covered, 2), score_range=[round(points, 2), round(min(100, points + 100 - covered), 2)],
        band=band or "자료 보완 필요", scored_count=sum(i["score"] is not None for i in all_items),
        evidence_basis={key: round(value, 2) for key, value in basis.items()},
        total_count=len(CRITERIA), groups=groups, upside=upside,
        collection_summary={"supported_count": len(AUTOMATIC[data.market]),
                            "supported_scored_count": sum(i["score"] is not None and i["id"] in AUTOMATIC[data.market] for i in all_items),
                            "research_count": len(CRITERIA) - len(AUTOMATIC[data.market])},
        warnings=[
            "매력도 점수는 상승 확률·투자의견·목표주가가 아닙니다.",
            "가중치와 기준 구간은 제안된 연구 규칙이며 예측 성능이 검증된 기준이 아닙니다.",
            "잠정 점수는 확보된 항목만 환산하므로 최종 점수와 직접 비교하지 마세요.",
            *data.notes,
        ],
    )
