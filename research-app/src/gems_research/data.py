"""Small DartLab bridge. Internal frame helpers are isolated behind a pinned version."""
from __future__ import annotations

import math
import os
import re
import threading
from datetime import date, datetime
from pathlib import Path

from .models import AnalysisInput, Observation, Source, today_kst
from .rubric import CRITERIA

_LOCK = threading.Lock()


def cagr(values: dict[str, float | None], years: int = 3) -> float | None:
    complete = sorted(y for y in values if re.fullmatch(r"\d{4}", y))
    if not complete:
        return None
    end = complete[-1]
    start = str(int(end) - years)
    # A gap in intermediate years means the comparable annual history is incomplete.
    if any(values.get(str(year)) is None for year in range(int(start), int(end) + 1)):
        return None
    first, last = values.get(start), values.get(end)
    if first is None or last is None or first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1 / years) - 1) * 100


def _source_date(raw) -> date:
    if "rcept_no" in raw.columns:
        dates = []
        for value in raw["rcept_no"].drop_nulls().unique().to_list():
            try:
                dates.append(datetime.strptime(str(value)[:8], "%Y%m%d").date())
            except ValueError:
                continue
        if dates:
            return max(dates)
    # Acquisition date is explicitly a fallback, not a claimed publication date.
    return today_kst()


def _financial_observations(raw, symbol: str) -> tuple[dict, str, list]:
    from dartlab.providers.dart.finance.frameTimeseries import buildTimeseriesFromFrame
    from dartlab.providers.dart.finance.pivot import _aggregateAnnual

    quarterly = buildTimeseriesFromFrame(raw, stockCode=symbol)
    if quarterly is None:
        raise ValueError("재무 파일 스키마를 해석할 수 없습니다.")
    qseries, periods = quarterly
    series, years = _aggregateAnnual(qseries, periods)
    published = _source_date(raw)
    source = Source(title="DartLab 재무 파일 · 공시 접수일 기준", url="https://opendart.fss.or.kr/", as_of=published)
    result = {}
    for key, account in [("revenue_cagr", "sales"), ("profit_cagr", "net_profit")]:
        mapping = dict(zip(years, series.get("IS", {}).get(account, [])))
        value = cagr(mapping)
        annual = sorted(y for y in mapping if re.fullmatch(r"\d{4}", y))
        evidence = "완결 연도 " + ", ".join(annual[-4:]) + ". 분기 누적값은 연간값에서 제외."
        if value is not None:
            end = annual[-1]
            start = str(int(end) - 3)
            evidence += f" {start}={mapping[start]:,.0f}, {end}={mapping[end]:,.0f} (원천 금액 단위)."
            result[key] = Observation(value=value, evidence=evidence, sources=[source],
                                      context={"start_year": start, "end_year": end,
                                               "start_value": mapping[start], "end_value": mapping[end]})
        elif key == "profit_cagr" and annual and mapping[annual[-1]] is not None and mapping[annual[-1]] < 0:
            result[key] = Observation(value=None, context={"loss": True}, evidence=evidence + " 최근 연간 순이익 적자.", sources=[source])
    bs = qseries.get("BS", {})
    # Use the same latest quarter for liabilities and equity, not independent last non-null values.
    idx = len(periods) - 1
    liabilities = bs.get("total_liabilities", [])
    equity = bs.get("total_stockholders_equity", bs.get("total_equity", []))
    if idx >= 0 and len(liabilities) > idx and len(equity) > idx:
        debt, capital = liabilities[idx], equity[idx]
        if debt is not None and capital is not None:
            context = {"nonpositive_equity": capital <= 0}
            ratio = debt / capital * 100 if capital > 0 else 0
            result["debt_ratio"] = Observation(value=ratio, context=context, sources=[source],
                evidence=f"{periods[idx]} 부채총계 {debt:,.0f} / 자본총계 {capital:,.0f}. 연결 우선. 이자보상배율·업종 예외는 추가 확인 필요.")
    name = symbol
    if "corp_name" in raw.columns and raw["corp_name"].drop_nulls().len():
        name = str(raw["corp_name"].drop_nulls()[0])
    notes = [
        "DartLab 최신 수정치 기반입니다. 과거 발표 시점의 정보를 재현한 백테스트 데이터가 아닙니다.",
        "자동 재무 평가는 연결 우선 3년 CAGR·부채비율입니다. 최신 분기를 연간 실적으로 간주하지 않습니다.",
    ]
    return result, name, notes


def _price_observations(raw) -> tuple[dict, float | None, date | None, list]:
    """Only score the KR price series when the split adjustment inputs are available."""
    import polars as pl

    cols = raw.columns
    date_col = "BAS_DD" if "BAS_DD" in cols else "date"
    close_col = "TDD_CLSPRC" if "TDD_CLSPRC" in cols else "close"
    if date_col not in cols or close_col not in cols:
        return {}, None, None, ["가격 파일 스키마 미지원. 가격·모멘텀은 수동 확인하세요."]
    frame = raw.sort(date_col)
    if frame[date_col].n_unique() != frame.height:
        return {}, None, None, ["날짜가 중복된 가격 파일이어서 자동 평가를 보류합니다."]
    if frame.is_empty():
        return {}, None, None, ["가격 파일이 비어 있습니다."]
    last_date = str(frame[date_col][-1]).replace("-", "")[:8]
    priced = datetime.strptime(last_date, "%Y%m%d").date()
    current = float(frame[close_col][-1])
    if not math.isfinite(current) or current <= 0:
        return {}, None, None, ["유효한 최근 종가가 없습니다."]
    observations = {}
    notes = ["현재가는 실시간 가격이 아닌 " + priced.isoformat() + " 데이터 파일의 최근 종가입니다."]
    if {"BAS_DD", "ISU_CD", "TDD_CLSPRC", "FLUC_RT"}.issubset(cols):
        from dartlab.gather.transforms.adjustPrice import applyAdjustment, detectEventsFromPrices
        frame = applyAdjustment(frame, detectEventsFromPrices(frame), mode="split")
        raw_closes = frame[close_col].to_list()
        if any(v is None for v in raw_closes):
            return {}, current, priced, notes + ["결측 종가가 있어 모멘텀 자동 평가를 보류합니다."]
        closes = [float(v) for v in raw_closes]
        if not all(math.isfinite(v) and v > 0 for v in closes):
            return {}, current, priced, notes + ["비정상 종가가 있어 모멘텀 자동 평가를 보류합니다."]
        source = Source(title="DartLab 가격 · 분할 추론 조정 · 배당 미포함", as_of=priced,
                        url="https://huggingface.co/datasets/eddmpython/dartlab-data", kind="estimate")
        evidence = "DartLab 분할 감지 기반 종가. 추론 조정이며 배당 재투자를 반영하지 않음."
        # Require an actual year of observations, not merely the first partial year available.
        dates = [datetime.strptime(str(v).replace("-", "")[:8], "%Y%m%d").date() for v in frame[date_col].to_list()]
        year_closes = [v for d, v in zip(dates, frame[close_col].to_list()) if (priced - d).days <= 365 and v is not None]
        if dates and (priced - dates[0]).days >= 364 and len(year_closes) >= 200:
            observations["high_distance"] = Observation(value=max(0, (1 - closes[-1] / max(year_closes)) * 100), sources=[source], evidence=evidence)
        if len(closes) >= 220:
            moving = [(sum(closes[i-49:i+1]) / 50, sum(closes[i-199:i+1]) / 200) for i in range(len(closes)-21, len(closes))]
            crossing = None
            for (old50, old200), (new50, new200) in zip(moving, moving[1:]):
                if old50 <= old200 and new50 > new200:
                    crossing = "golden_cross"
                elif old50 >= old200 and new50 < new200:
                    crossing = "death_cross"
            m50, m200 = moving[-1]
            trend = crossing or ("strong_up" if closes[-1] > m50 > m200 else "strong_down" if closes[-1] < m50 < m200 else "mixed")
            observations["trend"] = Observation(value=trend, sources=[source], evidence=evidence + " 최근 20거래일 교차 우선.")
    else:
        notes.append("수정주가·분할 처리 근거가 부족해 모멘텀을 자동 채점하지 않았습니다.")
    return observations, current, priced, notes


def configure_data_dir() -> Path:
    """Share one public-file cache between the native DartLab server and scoring."""
    import dartlab

    configured = os.environ.get("GEMS_DARTLAB_DATA_DIR")
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache"))
    path = Path(configured).expanduser().resolve() if configured else base / "gems-research" / "dartlab"
    dartlab.dataDir = str(path)
    return path


def load_company(symbol: str, market: str = "KR", offline: bool = False) -> AnalysisInput:
    try:
        import dartlab
        from dartlab.core.dataLoader import loadData
    except ImportError as exc:
        raise RuntimeError("DartLab이 없습니다. pip install -e '.[data]'로 설치하세요.") from exc
    with _LOCK:
        configure_data_dir()
        refresh = "local_only" if offline else "auto"
        category = "finance" if market == "KR" else "edgarFinanceStmt"
        raw = loadData(symbol, category, refresh=refresh)
        observations, name, notes = _financial_observations(raw, symbol)
        if market == "US":
            for obs in observations.values():
                obs.sources = [Source(title="DartLab SEC 표준화 재무 파일 · 취득일 기준",
                                      url="https://www.sec.gov/edgar/search/", as_of=today_kst())]
            notes.append("미국 데이터는 표준화 파일 범위에 한정됩니다. 회계연도·공시 원문·통화를 추가 확인하세요.")
        current = priced = None
        price_category = "govPriceCompany" if market == "KR" else "edgarPriceCompany"
        try:
            prices = loadData(symbol, price_category, refresh=refresh)
            extra, current, priced, price_notes = _price_observations(prices)
            observations.update(extra)
            notes.extend(price_notes)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            notes.append("가격 미조회: " + str(exc)[:180] + ". 재무 분석은 계속 사용할 수 있습니다.")
        return AnalysisInput(symbol=symbol, market=market, name=name, observations=observations,
                             current_price=current, price_date=priced, notes=notes)


def load_prices(symbol: str, market: str, offline: bool):
    try:
        from dartlab.core.dataLoader import loadData
    except ImportError as exc:
        raise RuntimeError("차트 전망에는 DartLab이 필요합니다. pip install -e '.[data]'로 설치하세요.") from exc
    with _LOCK:
        configure_data_dir()
        return loadData(symbol, "govPriceCompany" if market == "KR" else "edgarPriceCompany",
                        refresh="local_only" if offline else "auto")


def demo_input() -> AnalysisInput:
    """Synthetic company, never a live quote or an actual investment conclusion."""
    today = today_kst()
    src = Source(title="가상 예시 데이터 · 실제 기업 자료 아님", as_of=today, kind="assumption")
    numbers = dict(market_share=18, margin_advantage=3, revenue_cagr=12, profit_cagr=15,
                   peg=1.2, forward_pe_ratio=0.9, dividend=2, net_buyback=1.2,
                   relative_return=8, high_distance=12, institution_change=1, tam_growth=12, debt_ratio=70)
    observations = {}
    for item in CRITERIA:
        kwargs = dict(sources=[src], evidence="사용 흐름 확인용 가상 수치입니다. 실제 투자 판단에 사용할 수 없습니다.")
        if item["kind"] == "qualitative":
            observations[item["id"]] = Observation(score=3, **kwargs)
        elif item["kind"] == "choice":
            observations[item["id"]] = Observation(value="strong_up", **kwargs)
        else:
            observations[item["id"]] = Observation(value=numbers[item["id"]], **kwargs)
    observations["dividend"].context = dict(regular=True, cut_recently=False, growth_years=3)
    return AnalysisInput(symbol="DEMO", name="가상 기업 예시", observations=observations, demo=True,
                         current_price=100, price_date=today, target_price=115,
                         target_basis="가상의 시나리오 입력값이며 실제 목표주가가 아닙니다.",
                         thesis=["검증할 투자 논리를 입력하세요."], risks=["가상 예시는 실데이터 검증을 대신하지 않습니다."])
