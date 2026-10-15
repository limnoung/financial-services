"""Deterministic report and Gemini handoff using the existing financial-services workflows."""
from __future__ import annotations

from .models import AnalysisInput


def _cell(value) -> str:
    return str(value).replace("|", r"\|").replace("\n", " ")


def markdown_report(data: AnalysisInput, result: dict, *, include_review: bool = True) -> str:
    score = f'{result["score"]:.2f}/100' if result["score"] is not None else "미확정"
    provisional = result["provisional_score"]
    lines = [
        f"# {data.name or data.symbol} 투자 매력도 검토",
        "",
        "**가상 예시 데이터입니다.**" if data.demo else "공시·입력 근거를 바탕으로 작성한 검토 기록입니다.",
        "",
        "## 1 투자 요약",
        "",
        f'- 기업: {data.name or data.symbol} ({data.symbol}, {data.market})',
        f"- 분석 기준일: {data.as_of.isoformat()}",
        f'- 기준 버전: {result["rubric_version"]}',
        f'- 매력도: {score} / {result["band"]}',
        f'- 자료 충족률: {result["coverage"]:.2f}% ({result["scored_count"]}/{result["total_count"]}항목)',
        f'- 입력 자료 성격별 가중치: 사실 {result["evidence_basis"]["fact"]}% / 추정 {result["evidence_basis"]["estimate"]}% / 가정 {result["evidence_basis"]["assumption"]}%',
        f'- 미평가를 포함한 가능한 범위: {result["score_range"][0]:.2f}~{result["score_range"][1]:.2f}',
        f"- 확보된 항목만 환산한 잠정 점수: {provisional if provisional is not None else '없음'}",
        "- 투자의견: 별도 검토 필요. 매력도 점수만으로 매수·매도를 결정하지 않음.",
        f"- 가격: {data.current_price or '미입력'} / 가격 기준일: {data.price_date or '미확인'}",
        f"- 12개월 목표주가 입력: {data.target_price or '미입력'}",
        f"- 목표주가 근거: {data.target_basis or '미입력. 점수로 목표주가를 역산하지 않음.'}",
        f'- 목표가 대비 여력: {str(result["upside"]) + "%" if result["upside"] is not None else "미산출"}',
        "",
        "## 2 투자 논리",
        "",
        *[f"- {text}" for text in data.thesis if text.strip()],
    ]
    if not any(text.strip() for text in data.thesis):
        lines.append("검증 가능한 핵심 투자 논리 3개를 입력하세요.")
    lines += ["", "## 3 항목별 평가", "", "| 항목 | 가중치 | 평균 점수 | 자료 충족률 |", "|---|---:|---:|---:|"]
    for group in result["groups"]:
        lines.append(f'| {group["label"]} | {group["weight"]}% | {group["average"] if group["average"] is not None else "미평가"} | {group["coverage"]}% |')
    for group in result["groups"]:
        lines += ["", f'### {group["label"]}', "", "| 세부 항목 | 점수 | 근거 또는 보완 사항 | 출처와 기준일 |", "|---|---:|---|---|"]
        for item in group["items"]:
            sources = "; ".join(f'{s["title"]} ({s["as_of"]}) {s["url"]}' for s in item.get("sources", []))
            evidence = item.get("evidence", "") if item["score"] is not None else item["reason"] + " " + item.get("evidence", "")
            lines.append(f'| {item["label"]} | {item["score"] or "미평가"} | {_cell(evidence)} | {_cell(sources)} |')
    lines += ["", "## 4 경쟁사 비교", "", "| 기업 | 비교 지표 | 출처 |", "|---|---|---|"]
    lines += [f"| {_cell(peer.name)} | {_cell(peer.metrics)} | {_cell(peer.source)} |" for peer in data.peers]
    if not data.peers:
        lines.append("| 미입력 | 동일 사업·기간·통화 기준으로 2~3개 기업 비교 필요 | |")
    lines += ["", "## 5 핵심 리스크", ""]
    lines += [f"- {text}" for text in data.risks if text.strip()] or ["핵심 리스크와 투자 논리를 철회할 조건을 입력하세요."]
    lines += ["", "## 6 자료 한계와 검산", ""]
    lines += [f"- {warning}" for warning in result["warnings"]]
    lines += [
        "",
        "검토 참고: financial-services의 comps-analysis, dcf-model, audit-xls, earnings-preview 절차.",
        "본 보고서는 해당 스킬의 검토 항목을 참고하며 Claude 에이전트나 외부 LLM이 실행됐음을 의미하지 않습니다.",
        "",
    ]
    if include_review:
        from .review import financial_review
        review = financial_review(data, result)
        lines += ["## 7 재무 검토", "", "입력 점검 결과이며 원본 모델·Excel 수식 감사가 아닙니다.", ""]
        lines += [f'- {check["label"]}: {check["detail"]}' for check in review["checks"]]
    return "\n".join(lines)


def gemini_prompt(data: AnalysisInput, result: dict) -> str:
    return (
        "아래는 프로그램이 규칙으로 계산한 투자 검토 기록이다. 첨부한 GEMS_SCORING_GUIDE를 따른다.\n"
        "최신 공식 공시·IR·거래소 자료를 검색해 기준일과 출처를 확인하라. 검색할 수 없으면 최신이라고 표현하지 마라.\n"
        "자료 부족 항목의 수치·출처·점수를 지어내지 마라. 변경 제안은 기존 값, 새 값, 근거, 기준일을 별도로 제시하라.\n"
        "총점은 앱으로 다시 계산해야 하므로 임의로 수정하지 마라. 사실·추정·가정을 구분하고 핵심 반대 근거를 검토하라.\n"
        "점수에서 목표주가·상승 확률을 역산하지 마라. 가상 예시는 실제 기업으로 취급하지 마라.\n\n"
        + markdown_report(data, result)
    )
