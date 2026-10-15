"""Input review procedures adapted from the fork's financial-services skills.

This reviews the supplied evidence, not an Excel workbook or a live consensus
feed. Full original skill documents are bundled with their source revision.
"""
from pathlib import Path
import re

from .models import AnalysisInput
from .scoring import analyze

REFERENCE = Path(__file__).parent / "reference"
WORKFLOWS = [
    dict(id="comps-analysis", title="경쟁사 비교", description="사업·기간·회계 기준이 맞는 비교군과 배수를 검토합니다.", questions=[
        "경쟁사 2~3곳의 사업 구조와 회계연도·통화·연결 범위가 비교 가능한가?",
        "Forward P/E와 EPS의 예상 기간·조정 기준·컨센서스 날짜가 같은가?",
        "적자 기업의 P/E를 제외하고 중앙값과 이상치 제외 근거를 남겼는가?",
    ]),
    dict(id="dcf-model", title="가치평가 가정", description="독립적으로 만든 DCF·목표주가의 입력 가정을 확인합니다.", questions=[
        "매출·마진·세율·D&A·CapEx·운전자본의 가정과 출처를 구분했는가?",
        "차입금과 현금의 부호, 희석 주식수, 현금흐름 할인 시점이 일관되는가?",
        "WACC가 영구성장률보다 크고 민감도 중앙값이 기준 시나리오와 일치하는가?",
        "내재가치와 12개월 목표주가의 차이, 약세·기준·강세 조건을 설명했는가?",
    ]),
    dict(id="audit-xls", title="자료·산식 검산", description="현재 입력의 누락과 날짜를 검사하고 추가 검산 항목을 제시합니다.", questions=[
        "같은 기간에 자산 = 부채 + 자본, 현금흐름과 현금 잔액이 연결되는가?",
        "금액·주식수의 원/백만 단위와 퍼센트/%p 정의가 일치하는가?",
        "수식 오류·하드코딩·할인 시점·순현금 부호를 원본 모델에서 확인했는가?",
    ]),
    dict(id="earnings-preview", title="실적·반대 시나리오", description="실적 발표와 촉매가 기존 투자 논리를 바꿀 조건을 정리합니다.", questions=[
        "실적 발표일·예상 분기와 컨센서스의 출처·기준일을 확인했는가?",
        "매출·EPS·마진·FCF·가이던스 중 무엇이 판단을 바꾸는가?",
        "약세·기준·강세 시나리오와 논지를 철회할 수치·사건을 기록했는가?",
    ]),
]


def workflow_text(key: str) -> str:
    if key not in {flow["id"] for flow in WORKFLOWS}:
        raise KeyError(key)
    return (REFERENCE / (key + ".md")).read_text(encoding="utf-8")


def financial_review(data: AnalysisInput, result: dict | None = None) -> dict:
    result = result or analyze(data)
    checks = []

    def add(label, status, detail):
        checks.append(dict(label=label, status=status, detail=detail))

    dated = [s for obs in data.observations.values() for s in obs.sources]
    future = [s.title for s in dated if s.as_of > data.as_of]
    add("자료 기준일", "warning" if future else "ready" if dated else "missing",
        "기준일 이후 출처: " + ", ".join(future) if future else
        f"입력 출처 {len(dated)}건의 날짜 확인. 최신 공시 반영 여부는 원문에서 별도 확인하세요." if dated else "공시·IR 등 출처와 기준일이 필요합니다.")
    periods = [data.observations.get(key) for key in ("revenue_cagr", "profit_cagr")]
    def span(obs):
        if not obs:
            return None
        start, end = str(obs.context.get("start_year", "")), str(obs.context.get("end_year", ""))
        if re.fullmatch(r"\d{4}", start) and re.fullmatch(r"\d{4}", end) and int(end) - int(start) == 3:
            return start, end
        return None

    paired = [span(o) for o in periods]
    spans = {s for s in paired if s is not None}
    add("성장률 비교 기간", "warning" if len(spans) > 1 else "ready" if len(spans) == 1 and all(paired) else "missing",
        "매출·순이익 CAGR 기간: " + ", ".join(f"{start}~{end}" for start, end in sorted(spans)) if spans else "매출·순이익 CAGR의 완결 연도와 금액 단위가 필요합니다.")
    add("업종별 기준", "ready" if data.profile == "general" else "warning",
        "일반 비금융 기준입니다. 기업별 적합성을 확인하세요." if data.profile == "general" else "금융업·리츠·적자 성장기업은 PER·PEG·부채비율 대체 기준이 필요합니다.")
    peers = [p for p in data.peers if p.name.strip() and p.metrics.strip() and p.source.strip()]
    add("경쟁사 근거", "ready" if len(peers) >= 2 else "missing", f"이름·지표·출처가 입력된 경쟁사 {len(peers)}곳. 숫자의 기간·통화·비교 적합성은 추가 확인이 필요합니다.")
    add("가치평가와 점수 분리", "ready" if result["upside"] is not None else "missing",
        "입력 목표가와 가격으로 여력을 계산했습니다. DCF의 산식·가정·12개월 시점은 별도 검토하세요." if result["upside"] is not None else "가격·가격 기준일·목표가·독립적인 계산 근거를 보완하세요. 점수로 목표가를 만들지 않습니다.")
    add("투자 논리와 반대 근거", "ready" if any(t.strip() for t in data.thesis) and any(r.strip() for r in data.risks) else "missing",
        "입력한 논리·리스크에서 발생 조건과 판단을 바꿀 지표를 확인하세요." if any(t.strip() for t in data.thesis) and any(r.strip() for r in data.risks) else "핵심 투자 논리와 이를 무너뜨릴 리스크를 각각 작성하세요.")
    add("자료 충족률", "ready" if result["score"] is not None else "missing", f'{result["scored_count"]}/{result["total_count"]}항목, 가중 충족률 {result["coverage"]}%. 미평가를 임의의 중립 점수로 채우지 않습니다.')
    add("원본 모델 검산", "missing", "Excel·DCF 파일은 입력받지 않았습니다. BS 대차·CF 연결·WACC·할인 시점·수식 오류를 감사한 결과는 아닙니다.")
    prompt = [f"{data.name or data.symbol} ({data.symbol}, {data.market})를 분석 기준일 {data.as_of}에 맞춰 재무 검토하라.",
              "financial-services의 경쟁사 비교, DCF 가정 검토, 모델 검산, 실적 시나리오 절차를 사용하라.",
              "최신 공시와 컨센서스는 조회 가능할 때 출처·공개일을 확인하라. 미조회 자료·수치·모델을 만들어 검증했다고 주장하지 마라.",
              "매력도 점수는 프로그램에서 다시 계산한다. 점수에서 목표주가를 역산하지 마라.", "", "현재 입력 점검:"]
    prompt += [f'- {c["label"]}: {c["detail"]}' for c in checks]
    for flow in WORKFLOWS:
        prompt += ["", flow["title"], *["- " + q for q in flow["questions"]]]
    # Import here to keep reports -> review enrichment free of import cycles.
    from .reports import markdown_report
    prompt += ["", markdown_report(data, result, include_review=False)]
    return dict(checks=checks, workflows=WORKFLOWS, prompt="\n".join(prompt))
