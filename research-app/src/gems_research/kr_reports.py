"""Conservative ordinary-share dividend extraction from public DART reports."""
from datetime import date, datetime
import math
import re

from .models import Observation, Source


def number(value):
    try:
        result = float(str(value).replace(",", "").strip())
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None  # DART '-' is missing, never an asserted zero dividend.


def dividend_observation(raw, symbol: str, as_of: date) -> tuple[Observation | None, str]:
    required = {"apiType", "year", "quarter", "rcept_no", "se", "stock_knd", "thstrm"}
    if not required.issubset(raw.columns):
        return None, "배당 공시 파일의 보통주·연도·접수번호를 확인할 수 없습니다."
    annual = {}
    for row in raw.iter_rows(named=True):
        if row.get("apiType") != "dividend" or str(row.get("quarter")) not in {"4분기", "사업보고서", "4", "Q4"}:
            continue
        if row.get("stockCode") is not None and str(row["stockCode"]) != symbol:
            return None, "배당 파일의 종목코드가 요청 종목과 일치하지 않습니다."
        receipt = str(row.get("rcept_no") or "")
        year = str(row.get("year") or "")
        if not re.fullmatch(r"\d{14}", receipt) or not re.fullmatch(r"\d{4}", year):
            continue
        try:
            published = datetime.strptime(receipt[:8], "%Y%m%d").date()
        except ValueError:
            continue
        if published > as_of or int(year) > published.year:
            continue
        if row.get("stlm_dt"):
            try:
                if date.fromisoformat(str(row["stlm_dt"])) > published:
                    continue
            except ValueError:
                continue
        # Use one latest filing per year; never mix original and corrected rows.
        record = annual.get(int(year))
        if record is None or receipt > record["receipt"]:
            record = annual[int(year)] = {"receipt": receipt, "published": published, "rows": []}
        if receipt == record["receipt"]:
            record["rows"].append(row)
    if not annual:
        return None, "기준일 이전의 보통주 연간 배당 공시가 없습니다. 분기 누적 배당을 연간값으로 사용하지 않습니다."

    def unique(rows, label, common=True):
        values = {number(r.get("thstrm")) for r in rows
                  if re.sub(r"\s+", "", str(r.get("se") or "")) == label
                  and (not common or re.sub(r"\s+", "", str(r.get("stock_knd") or "")) == "보통주")}
        return next(iter(values)) if len(values) == 1 and None not in values else None

    for record in annual.values():
        record["dps"] = unique(record["rows"], "주당현금배당금(원)")
        record["yield"] = unique(record["rows"], "현금배당수익률(%)")
        record["par"] = unique(record["rows"], "주당액면가액(원)", common=False)
    end = max(annual)
    current, previous = annual[end], annual.get(end - 1)
    dps, yield_value = current["dps"], current["yield"]
    if dps is None or yield_value is None or yield_value > 100:
        return None, f"{end}년 보통주 연간 배당금·배당수익률이 누락됐습니다. 우선주 수치를 대입하지 않습니다."
    if dps == 0 and yield_value != 0:
        return None, "보통주 배당금 0원과 배당수익률이 일치하지 않아 확인이 필요합니다."
    if dps > 0 and yield_value == 0:
        return None, "배당금이 있지만 공시 배당수익률이 0으로 표시돼 정확한 수익률 확인이 필요합니다."
    if dps > 0 and (previous is None or previous["dps"] is None or current["par"] is None
                    or current["par"] <= 0 or previous["par"] != current["par"]):
        return None, "전년 대비 배당 삭감·분할 여부를 확인할 동일 액면의 연간 보통주 배당 이력이 부족합니다."
    if dps > 0 and any(annual.get(y, {}).get("dps") is None for y in range(end - 2, end + 1)):
        return None, "정기 지급 여부를 확인할 최근 3개 완결 연도 보통주 배당금이 부족합니다."
    context = {"regular": all(annual.get(y, {}).get("dps", 0) is not None and annual.get(y, {}).get("dps", 0) > 0
                              for y in range(end - 2, end + 1)),
               "cut_recently": bool(previous and previous["dps"] is not None and dps < previous["dps"]),
               "growth_years": 0, "fiscal_year": end, "dps": dps,
               "yield_basis": "annual_report"}
    for year in range(end, end - 5, -1):
        newer, older = annual.get(year), annual.get(year - 1)
        if not newer or not older or newer["dps"] is None or older["dps"] is None or older["dps"] <= 0:
            break
        if newer["par"] is None or newer["par"] != older["par"] or newer["dps"] <= older["dps"]:
            break
        context["growth_years"] += 1
    relevant = [annual[y] for y in range(end - max(2, context["growth_years"]), end + 1) if y in annual]
    sources = [Source(title=f"DART 보통주 연간 배당 · {end} 사업보고서", as_of=current["published"],
                      url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + current["receipt"])]
    sources.extend(Source(title="DART 배당 지속성 비교 공시", as_of=record["published"],
                          url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + record["receipt"])
                   for record in reversed(relevant) if record["receipt"] != current["receipt"])
    evidence = (f"{end}년 사업보고서 보통주 현금배당금 {dps:,.0f}원, 공시 배당수익률 {yield_value:g}%. "
                "현재 주가 기준 수익률이나 미래 배당 예상치가 아닙니다. "
                f"최근 3개 완결 연도 연속 지급={context['regular']}, 최근 연간 삭감={context['cut_recently']}, "
                f"동일 액면에서 확인된 연속 증가 {context['growth_years']}년.")
    return Observation(value=yield_value, evidence=evidence, sources=sources, context=context), ""
