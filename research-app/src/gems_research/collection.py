"""Explain the data bridge's scope independently of scoring weights."""

AUTOMATIC = {
    "KR": {"revenue_cagr", "profit_cagr", "debt_ratio", "dividend", "high_distance", "trend"},
    "US": {"revenue_cagr", "profit_cagr", "debt_ratio", "high_distance", "trend"},
}

RESEARCH_NOTES = {
    "market_share": "동일 제품·지역·기간으로 정의한 시장 점유율과 출처를 입력하세요.",
    "margin_advantage": "비교 가능한 경쟁사와 같은 기간의 영업이익률을 확인하세요.",
    "peg": "예상 EPS 성장률과 같은 기간의 Forward P/E·컨센서스 출처가 필요합니다.",
    "forward_pe_ratio": "동일 예상 기간의 회사·경쟁사 Forward P/E가 필요합니다.",
    "net_buyback": "분할·무상증자를 조정한 보통주 유통주식수의 연간 비교가 필요합니다.",
    "insider": "최근 6개월 내부자 거래의 유형·규모·출처를 검토하고 점수를 선택하세요.",
    "institution_change": "분기별 기관 보유율 자료가 필요합니다. 외국인 보유율·일별 순매수로 대체하지 않습니다.",
    "relative_return": "동일 날짜·배당 처리 기준의 종목과 시장 벤치마크 1년 수익률이 필요합니다.",
    "tam_growth": "실제 진출 가능한 시장의 범위·성장 기간·독립 출처가 필요합니다.",
    "dividend": "배당수익률과 연도별 보통주 배당 이력을 확인하세요.",
}


def missing_reason(key: str, market: str) -> str:
    if key in AUTOMATIC[market]:
        return "DartLab 불러오기에서 해당 자료를 조회하거나 근거를 직접 입력하세요."
    return RESEARCH_NOTES.get(key, "공시·IR·뉴스 근거를 검토하고 정성 점수를 선택하세요.")
