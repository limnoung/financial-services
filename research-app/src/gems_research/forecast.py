"""DartLab return forecasts with horizon-specific historical error bands.

Models are fixed in advance, not selected on the displayed validation sample.
Every origin fits only prices known at that origin. Validation endpoints do not
overlap; their error bands are calibrated before the first validation origin.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import math

from .data import load_prices
from .models import ForecastInput

VERSION = "price-forecast-1.0"
MIN_CALIBRATION = 30
MAX_CALIBRATION = 252
NOMINAL_COVERAGE = 0.8


def _numpy():
    try:
        import numpy as np
        return np
    except ImportError as exc:
        raise RuntimeError("차트 전망 의존성을 설치하세요: pip install -e '.[data]'") from exc


def prepare_prices(raw, request: ForecastInput) -> tuple[list[date], list[float], str]:
    """Filter the cutoff before adjustment and refuse ambiguous price schemas."""
    import polars as pl

    kr = request.market == "KR"
    date_col, close_col = ("BAS_DD", "TDD_CLSPRC") if kr else ("date", "close")
    required = {date_col, close_col} | ({"ISU_CD", "FLUC_RT"} if kr else set())
    if not required.issubset(raw.columns):
        raise ValueError("수정 가격의 근거를 확인할 수 없는 파일입니다. 분할 정보가 있는 DartLab 가격 파일이 필요합니다.")
    parsed = []
    for value in raw[date_col].to_list():
        text = str(value).replace("-", "")
        if len(text) != 8 or not text.isdigit():
            raise ValueError("가격 파일의 날짜 형식을 확인하세요.")
        parsed.append(datetime.strptime(text, "%Y%m%d").date())
    frame = raw.with_columns(pl.Series("__forecast_date", parsed, dtype=pl.Date)).filter(pl.col("__forecast_date") <= request.as_of).sort("__forecast_date")
    if frame.is_empty():
        raise ValueError("기준일 이전 가격이 없습니다.")
    dates = frame["__forecast_date"].to_list()
    if len(set(dates)) != len(dates):
        raise ValueError("중복 날짜가 있는 가격 파일은 예측에 사용할 수 없습니다.")
    prices = frame[close_col].to_list()
    if any(v is None or isinstance(v, bool) or not math.isfinite(float(v)) or float(v) <= 0 for v in prices):
        raise ValueError("종가에 결측·0 이하·비정상 값이 있습니다. 임의 보간하지 않습니다.")
    if any((b - a).days > 14 for a, b in zip(dates, dates[1:])):
        raise ValueError("가격에 14일을 넘는 공백이 있습니다. 거래정지·누락을 확인한 뒤 연속 구간을 사용하세요.")
    if kr:
        codes = {str(code).removeprefix("A") for code in frame["ISU_CD"].to_list()}
        if codes != {request.symbol}:
            raise ValueError("가격 파일의 종목코드가 요청 종목과 일치하지 않습니다.")
        changes = frame["FLUC_RT"].to_list()
        if any(v is None or not math.isfinite(float(v)) for v in changes[1:]):
            raise ValueError("분할 감지에 필요한 등락률이 누락됐습니다.")
        from dartlab.gather.transforms.adjustPrice import applyAdjustment, detectEventsFromPrices
        frame = frame.with_columns(pl.col(close_col).cast(pl.Float64), pl.col("FLUC_RT").cast(pl.Float64))
        frame = applyAdjustment(frame, detectEventsFromPrices(frame), mode="split")
        prices = frame[close_col].to_list()
        basis = "DartLab 정부 가격 파일 · 분할 추론 조정 · 배당 미포함"
    else:
        basis = "DartLab EDGAR 가격 artifact의 제공자 수정종가(close) · Yahoo 기반"
    values = [float(v) for v in prices]
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("가격 조정 결과가 유효하지 않습니다.")
    return dates, values, basis


def model_path(prices, origin: int, lookback: int, horizon: int, method: str):
    np = _numpy()
    from dartlab.quant.benchmark.forecast import _modelAr1, _modelNaive

    # Exactly `lookback` returns. No later price is passed to the model.
    returns = np.diff(np.log(np.asarray(prices[origin - lookback:origin + 1], dtype=float)))
    daily, _ = (_modelAr1 if method == "ar1" else _modelNaive)(returns, horizon)
    cumulative = np.cumsum(daily)
    if not np.isfinite(cumulative).all() or np.max(np.abs(cumulative)) > 100:
        raise ValueError("예측 경로가 수치적으로 불안정합니다. 가격과 적합 기간을 확인하세요.")
    path = float(prices[origin]) * np.exp(cumulative)
    if not np.isfinite(path).all() or np.min(path) <= 0:
        raise ValueError("예측 가격이 유효하지 않습니다.")
    return path


def error_band(prices, cutoff: int, request: ForecastInput):
    np = _numpy()
    end = cutoff - request.horizon
    start = max(request.lookback, end - MAX_CALIBRATION + 1)
    count = max(0, end - start + 1)
    if count < MIN_CALIBRATION:
        return None, count, None
    errors = []
    for origin in range(start, end + 1):
        predicted = model_path(prices, origin, request.lookback, request.horizon, request.method)
        actual = np.asarray(prices[origin + 1:origin + request.horizon + 1])
        errors.append(np.abs(np.log(actual / predicted)))
    # Finite-sample conservative empirical order statistic at each horizon.
    rank = min(count, math.ceil((count + 1) * NOMINAL_COVERAGE)) - 1
    widths = np.sort(np.asarray(errors), axis=0)[rank]
    return np.maximum.accumulate(widths), count, (start, cutoff)


def forecast_series(dates: list[date], prices: list[float], request: ForecastInput, *, source: str) -> dict:
    np = _numpy()
    if len(dates) != len(prices) or any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("가격의 날짜 순서와 길이를 확인하세요.")
    if not prices or any(not math.isfinite(v) or v <= 0 for v in prices):
        raise ValueError("유효한 양수 종가가 필요합니다.")
    if dates[-1] > request.as_of:
        raise ValueError("기준일 이후 가격을 사용할 수 없습니다.")
    if len(prices) < request.lookback + 1:
        raise ValueError(f"적합에 종가 {request.lookback + 1}개 이상이 필요합니다. 현재 {len(prices)}개입니다.")
    last = len(prices) - 1
    point = model_path(prices, last, request.lookback, request.horizon, request.method)
    widths, calibration_count, _ = error_band(prices, last, request)
    future = []
    for i, value in enumerate(point):
        low, high = (float(value * np.exp(-widths[i])), float(value * np.exp(widths[i]))) if widths is not None else (None, None)
        if low is not None and (not math.isfinite(low) or not math.isfinite(high) or low <= 0):
            raise ValueError("오차 범위가 수치적으로 불안정합니다.")
        future.append(dict(step=i + 1, estimate=float(value), lower=low, upper=high, baseline=prices[-1]))

    # Reserve up to six non-overlapping H-step validation windows, while leaving
    # 30 calibration origins whose targets finish before validation starts.
    first_allowed = request.lookback + request.horizon + MIN_CALIBRATION - 1
    count = min(6, max(0, (last - first_allowed) // request.horizon))
    origins = [last - k * request.horizon for k in range(count, 0, -1)] if count >= 3 else []
    checks = []
    validation_calibration = None
    if origins:
        frozen, frozen_n, _ = error_band(prices, origins[0], request)
        validation_calibration = dict(count=frozen_n, cutoff=dates[origins[0]].isoformat())
        if frozen is None:
            raise ValueError("검증용 오차 계산 구간이 부족합니다.")
        for origin in origins:
            predicted = float(model_path(prices, origin, request.lookback, request.horizon, request.method)[-1])
            actual, baseline = prices[origin + request.horizon], prices[origin]
            low, high = float(predicted * np.exp(-frozen[-1])), float(predicted * np.exp(frozen[-1]))
            checks.append(dict(origin=dates[origin].isoformat(), target=dates[origin + request.horizon].isoformat(),
                               estimate=predicted, actual=actual, baseline=baseline, lower=low, upper=high,
                               covered=low <= actual <= high,
                               direction_correct=int(np.sign(math.log(predicted / baseline))) == int(np.sign(math.log(actual / baseline)))))
    validation = dict(count=len(checks), rows=checks, calibration=validation_calibration,
                      mape=None, baseline_mape=None, relative_mae=None, direction_accuracy=None, interval_coverage=None)
    if checks:
        absolute = [abs(c["estimate"] - c["actual"]) for c in checks]
        base_absolute = [abs(c["baseline"] - c["actual"]) for c in checks]
        validation.update(mape=float(np.mean([a / c["actual"] * 100 for a, c in zip(absolute, checks)])),
                          baseline_mape=float(np.mean([a / c["actual"] * 100 for a, c in zip(base_absolute, checks)])),
                          relative_mae=sum(absolute) / sum(base_absolute) if sum(base_absolute) > 0 else None,
                          direction_accuracy=sum(c["direction_correct"] for c in checks) / len(checks) * 100,
                          interval_coverage=sum(c["covered"] for c in checks) / len(checks) * 100)
    warnings = [
        "통계적 참고 경로입니다. 미래 가격·수익을 보장하지 않습니다.",
        "오차 범위의 목표 포함률은 80%이며 실제 미래 포함 확률을 보장하지 않습니다.",
        "범위 계산의 일별 출발점은 겹칩니다. 검증 구간은 겹치지 않지만 표본이 작습니다.",
        "최신 수정 가격 파일의 과거 구간 검증입니다. 당시 배포본·상장폐지·거래비용을 재현한 투자 성과 검증이 아닙니다.",
        "미래 X축은 거래 관측 순서(+N)이며 휴장일을 반영한 미래 달력 날짜가 아닙니다.",
    ]
    if widths is None:
        warnings.append(f"오차 계산에 필요한 과거 구간이 부족해 범위를 표시하지 않습니다. 최소 {MIN_CALIBRATION}개 출발점이 필요합니다.")
    if not checks:
        warnings.append("독립된 과거 검증 구간 3개를 확보하지 못해 검증 지표를 표시하지 않습니다.")
    if (request.as_of - dates[-1]).days > 7:
        warnings.append(f"가격 파일의 마지막 거래일은 {dates[-1]}입니다. 조회 기준일보다 오래된 자료에서 출발한 전망입니다.")
    if request.demo:
        warnings.insert(0, "가상 가격 예시입니다. 실제 종목·시세·투자 결과가 아닙니다.")
    return dict(version=VERSION, symbol="DEMO" if request.demo else request.symbol, market=request.market,
                currency="KRW" if request.market == "KR" else "USD", demo=request.demo,
                as_of=request.as_of.isoformat(), price_date=dates[-1].isoformat(), method=request.method,
                engine="DartLab 0.12.0 · AR(1) 로그수익률" if request.method == "ar1" else "DartLab 0.12.0 · 평균 로그수익률",
                lookback=request.lookback, horizon=request.horizon, last_close=prices[-1],
                projected_change=(future[-1]["estimate"] / prices[-1] - 1) * 100,
                history=[dict(date=d.isoformat(), close=v) for d, v in zip(dates[-252:], prices[-252:])],
                future=future, calibration=dict(count=calibration_count, nominal_coverage=80, minimum=MIN_CALIBRATION),
                validation=validation, source=dict(title=source, url="" if request.demo else "https://huggingface.co/datasets/eddmpython/dartlab-data"),
                warnings=warnings)


def forecast_prices(request: ForecastInput) -> dict:
    if request.demo:
        np = _numpy()
        dates, current = [], request.as_of
        while len(dates) < 900:
            if current.weekday() < 5:
                dates.append(current)
            current -= timedelta(days=1)
        dates.reverse()
        prices = (100 * np.exp(np.cumsum(np.random.default_rng(713).normal(0.0003, 0.014, len(dates))))).tolist()
        source = "가상 가격 시계열 · 고정 난수 · 실제 기업 자료 아님"
    else:
        raw = load_prices(request.symbol, request.market, request.offline)
        dates, prices, source = prepare_prices(raw, request)
    return forecast_series(dates, prices, request, source=source)
