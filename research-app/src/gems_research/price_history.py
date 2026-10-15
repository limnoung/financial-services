"""Fill short government price histories from matching KRX raw artifacts."""
from datetime import datetime
import math

from .models import today_kst


def canonical_kr(raw, symbol):
    import polars as pl
    required = {"BAS_DD", "ISU_CD", "TDD_CLSPRC", "FLUC_RT"}
    if not required.issubset(raw.columns):
        raise ValueError("종목코드·종가·분할 감지용 등락률을 확인할 수 없는 가격 파일입니다.")
    if raw.is_empty():
        raise ValueError("가격 파일이 비어 있습니다.")
    if {str(v).removeprefix("A") for v in raw["ISU_CD"].to_list()} != {symbol}:
        raise ValueError("가격 파일의 종목코드가 요청 종목과 일치하지 않습니다.")
    dates = []
    for value in raw["BAS_DD"].to_list():
        dates.append(datetime.strptime(str(value).replace("-", ""), "%Y%m%d").date())
    if len(set(dates)) != len(dates):
        raise ValueError("가격 날짜가 중복됐습니다.")
    frame = raw.with_columns(pl.Series("BAS_DD", [d.strftime("%Y%m%d") for d in dates]),
                             pl.lit(symbol).alias("ISU_CD"),
                             pl.col("TDD_CLSPRC").cast(pl.Float64, strict=False),
                             pl.col("FLUC_RT").cast(pl.Float64, strict=False))
    frame = frame.filter(pl.col("BAS_DD") <= today_kst().strftime("%Y%m%d")).sort("BAS_DD")
    if frame.is_empty() or any(v is None or not math.isfinite(v) or v <= 0 for v in frame["TDD_CLSPRC"].to_list()):
        raise ValueError("유효한 양수 종가 이력이 없습니다.")
    if any(v is None or not math.isfinite(v) for v in frame["FLUC_RT"].to_list()[1:]):
        raise ValueError("분할 감지용 등락률에 결측·비정상 값이 있습니다.")
    return frame


def full_window(frame):
    if frame is None or frame.height < 220:
        return False
    dates = [datetime.strptime(value, "%Y%m%d").date() for value in frame["BAS_DD"].to_list()]
    recent = [d for d in dates if (dates[-1] - d).days <= 365]
    return ((dates[-1] - dates[0]).days >= 364 and len(recent) >= 200 and (dates[-1] - recent[0]).days >= 350
            and not any((b - a).days > 14 for a, b in zip(recent, recent[1:]))
            and not any((b - a).days > 14 for a, b in zip(dates[-220:], dates[-219:])))


def load_kr_prices(load_data, symbol: str, refresh: str):
    import polars as pl
    frames, notes = [], []
    for category in ("govPriceCompany", "krxPriceCompany"):
        try:
            frame = canonical_kr(load_data(symbol, category, refresh=refresh), symbol)
            frames.append(frame)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            notes.append(f"{category} 가격 조회·검증 실패: {str(exc)[:140]}")
        if category == "govPriceCompany" and frames and full_window(frames[0]):
            break
    if not frames:
        raise ValueError(" / ".join(notes))
    if len(frames) == 1:
        return frames[0], notes
    primary, history = frames
    overlap = primary.select("BAS_DD", "TDD_CLSPRC", "FLUC_RT").join(
        history.select("BAS_DD", "TDD_CLSPRC", "FLUC_RT"), on="BAS_DD", suffix="_krx")
    compatible = overlap.height >= 5 and all(
        a == b and c is not None and d is not None and abs(c - d) <= .02
        for _, a, c, b, d in overlap.iter_rows())
    if compatible:
        older = history.filter(~pl.col("BAS_DD").is_in(primary["BAS_DD"].implode()))
        frame = pl.concat([older, primary], how="diagonal_relaxed").sort("BAS_DD")
        notes.append("정부·KRX 가격의 겹치는 날짜 5개 이상에서 원종가·등락률을 대조한 후 과거 이력을 보완했습니다. 중복 날짜는 정부 파일 우선입니다.")
        return frame, notes
    notes.append("정부·KRX 가격의 중복 날짜·가격 일치를 확인하지 못해 두 계열을 합치지 않았습니다.")
    # Never replace a current short series with an older long series to raise coverage.
    return max(frames, key=lambda frame: (frame["BAS_DD"][-1], frame.height)), notes
