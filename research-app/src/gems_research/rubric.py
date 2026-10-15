"""Explicit, versioned policy. Thresholds are a research convention, not fitted probabilities."""

VERSION = "gems-reference-1.0"
GROUPS = [
    ("moat", "경제적 해자", 20),
    ("growth", "성장성·밸류에이션", 25),
    ("alignment", "주주 친화 정책", 10),
    ("momentum", "시장 모멘텀", 20),
    ("catalysts", "미래 촉매·트렌드", 15),
    ("resilience", "회복탄력성·리스크", 10),
]

# Text is part of the policy and exposed in the app and Gemini attachment.
CRITERIA = [
    dict(id="market_share", group="moat", label="시장 점유율", kind="number", unit="%", rule="high", cuts=[5, 10, 25, 40],
         guide="같은 제품·지역·기간으로 정의한 시장. 5% 미만 1점, 5/10/25/40% 이상 각각 2/3/4/5점."),
    dict(id="switching", group="moat", label="전환 비용·네트워크 효과", kind="qualitative",
         guide="1 전환 장벽 없음 / 2 작은 혜택으로 이동 / 3 통합·학습 비용 존재 / 4 유지율·장기계약 등으로 높은 장벽 확인 / 5 복수의 독립 근거로 강한 생태계 의존 확인."),
    dict(id="brand", group="moat", label="브랜드·지식재산", kind="qualitative",
         guide="1 차별화 근거 없음 / 2 제한적인 인지도·범용 특허 / 3 특정 시장에서 인지도·보호권 확인 / 4 글로벌 인지도·상업화된 핵심 특허 / 5 가격 결정력과 수익 기여가 입증된 브랜드·독점 기술."),
    dict(id="margin_advantage", group="moat", label="경쟁사 대비 영업이익률", kind="number", unit="%p", rule="high", cuts=[-5, 0, 5, 10],
         guide="동일 기간·회계 기준의 경쟁사 중앙값 대비 차이. -5%p 미만 1점, -5/0/5/10%p 이상 2/3/4/5점."),
    dict(id="revenue_cagr", group="growth", label="매출 3년 CAGR", kind="number", unit="%", rule="high", cuts=[0, 5, 15, 25],
         guide="완결된 4개 연도에서 (최근/3년 전)^(1/3)-1. 역성장 1점, 0/5/15/25% 이상 2/3/4/5점."),
    dict(id="profit_cagr", group="growth", label="순이익 3년 CAGR", kind="number", unit="%", rule="high", cuts=[0, 10, 20, 30],
         guide="같은 순이익 정의의 완결 연도. 0/10/20/30% 이상 2/3/4/5점. 최근 적자는 context.loss=true로 1점. 적자에서 흑자 전환은 CAGR 산출 불가로 분리."),
    dict(id="peg", group="growth", label="PEG", kind="number", unit="배", rule="low", cuts=[0.8, 1.0, 1.5, 2.0],
         guide="Forward P/E ÷ 예상 연간 EPS 성장률(% 숫자). 0.8 미만 5점, 1.0 미만 4점, 1.5 미만 3점, 2.0 미만 2점, 그 이상 1점. 성장 추정 기간·출처 필수."),
    dict(id="forward_pe_ratio", group="growth", label="Forward P/E ÷ 경쟁사 중앙값", kind="number", unit="배", rule="low", cuts=[0.70, 0.85, 1.15, 1.30],
         guide="동일 NTM 또는 동일 회계연도 EPS 사용. 0.70 미만 5점, 0.85 미만 4점, 1.15 미만 3점, 1.30 미만 2점, 그 이상 1점. 적자 PER은 미평가."),
    dict(id="dividend", group="alignment", label="배당수익률·지속성", kind="number", unit="%", rule="dividend",
         guide="무배당 1점 / 최근 삭감 2점 / 소액·비정기 3점 / 1% 이상 정기 배당 4점 / 3% 이상+5년 연속 증가 5점. context에 regular, cut_recently, growth_years를 기록."),
    dict(id="net_buyback", group="alignment", label="연간 순유통주식수 감소율", kind="number", unit="%", rule="buyback",
         guide="분할 조정·자사주 제외 보통주식수 기준. 희석(<0) 1점 / 0% 2점 / 0~1% 3점 / 1~2% 4점 / 2% 이상 5점. 매입 발표가 아닌 실제 순감소."),
    dict(id="insider", group="alignment", label="내부자 거래 최근 6개월", kind="qualitative",
         guide="1 다수 경영진의 중요한 순매도 / 2 제한적 순매도 / 3 변동 없음 / 4 제한적 순매수 / 5 다수 경영진의 중요한 순매수. 거래유형·보유량 대비 규모·보상/세금/사전매매 계획을 설명. 자료 미확인은 3점 아님."),
    dict(id="relative_return", group="momentum", label="1년 벤치마크 초과수익", kind="number", unit="%p", rule="high", cuts=[-25, -10, 10, 25],
         guide="동일 날짜·통화·배당 처리로 비교. -25%p 미만 1점, -25/-10/10/25%p 이상 2/3/4/5점. KR은 사전 지정 KOSPI/KOSDAQ, US는 S&P500 등."),
    dict(id="high_distance", group="momentum", label="52주 최고 종가 대비 하락률", kind="number", unit="%", rule="low", cuts=[5, 15, 30, 50],
         guide="동일 수정주가 계열에서 (1-현재 종가/52주 최고 종가)×100. 5% 미만 5점, 15/30/50% 미만 4/3/2점, 그 이상 1점."),
    dict(id="institution_change", group="momentum", label="분기 기관 보유율 변화", kind="number", unit="%p", rule="high", cuts=[-5, -2, 2, 5],
         guide="보유주식 수가 아닌 보유율의 %p 변화. 분기 말·공개일·분모 변화 확인. 일별 기관 순매수로 대체하지 않음."),
    dict(id="trend", group="momentum", label="50일·200일 이동평균", kind="choice",
         options={"strong_down": "강한 역배열 (1)", "death_cross": "최근 데드크로스 (2)", "mixed": "횡보·혼조 (3)", "golden_cross": "최근 골든크로스 (4)", "strong_up": "강한 정배열 (5)"},
         guide="최근 20거래일의 마지막 교차를 우선 반영. 교차가 없으면 종가>50일>200일은 5점, 종가<50일<200일은 1점, 나머지 3점. 최소 220개 거래일 필요."),
    dict(id="megatrend", group="catalysts", label="산업 트렌드 수혜", kind="qualitative",
         guide="1 축소 산업·연결 근거 없음 / 2 간접 영향 / 3 일부 매출 연계 / 4 수주·고객·매출로 핵심 수혜 확인 / 5 표준·생태계를 이끌고 수익화 입증. 홍보 키워드만으로 고득점 금지."),
    dict(id="pipeline", group="catalysts", label="신제품·사업 촉매", kind="qualitative",
         guide="1 혁신 근거 없음 / 2 투자 대비 성과 부족 / 3 기존 제품 개선 / 4 상업화 이정표·고객 검증 / 5 1~2년 내 큰 매출 기여가 가능한 확정 일정과 검증. 예정·승인·매출 발생을 구분."),
    dict(id="tam_growth", group="catalysts", label="진출 시장 성장률", kind="number", unit="%", rule="high", cuts=[0, 5, 10, 20],
         guide="기업이 실제 진출 가능한 시장의 연 성장률. 축소 1점, 0/5/10/20% 이상 2/3/4/5점. 시장 범위·기간·독립 출처를 기록."),
    dict(id="debt_ratio", group="resilience", label="부채총계 ÷ 자본총계", kind="number", unit="%", rule="debt",
         guide="비금융업 기준. 50/100/150/200% 미만 각각 5/4/3/2점, 그 이상 1점. 자본<=0 또는 이자보상배율<1은 1점 우선. 금융업·리츠·적자 성장기업은 보완 프로필 필요."),
    dict(id="diversification", group="resilience", label="사업·고객·지역 집중 리스크", kind="qualitative",
         guide="1 단일 고객·공급망 장애가 존속을 위협 / 2 큰 집중과 대안 부족 / 3 집중은 있으나 완충 수단 확인 / 4 고객·지역 분산 및 대체 수단 / 5 매출원 분산과 스트레스 대응 실적 확인. 단일 사업 전문화 자체를 감점하지 않음."),
    dict(id="governance", group="resilience", label="지배구조·규제 대응", kind="qualitative",
         guide="1 중대한 확정 위반·소수주주 침해 / 2 중요한 미해결 분쟁·통제 결함 / 3 보통 수준의 통제·공시 / 4 독립적 감독과 대응 실적 / 5 복수의 근거로 강한 주주 보호·검증된 통제. ESG 점수만으로 자동 평가하지 않음."),
]
BY_ID = {item["id"]: item for item in CRITERIA}


def catalog() -> dict:
    return {
        "version": VERSION,
        "groups": [dict(id=g, label=label, weight=w) for g, label, w in GROUPS],
        "criteria": CRITERIA,
        "formula": "Σ(그룹 가중치 / 세부항목 수 × (점수 - 1) / 4)",
        "scale": "1점=0, 3점=50, 5점=100으로 환산. 투자 수익률이나 상승 확률이 아님.",
    }
