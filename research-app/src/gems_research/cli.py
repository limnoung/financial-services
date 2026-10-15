from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import demo_input, load_company
from .models import AnalysisInput
from .reports import markdown_report
from .scoring import analyze


def main():
    parser = argparse.ArgumentParser(description="Gems 투자 매력도 분석")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="로컬 분석 화면")
    serve.add_argument("--port", type=int, default=8766)
    calc = sub.add_parser("analyze", help="JSON 입력 또는 DartLab 조회")
    calc.add_argument("symbol", nargs="?")
    calc.add_argument("--market", choices=["KR", "US"], default="KR")
    calc.add_argument("--input", type=Path)
    calc.add_argument("--demo", action="store_true")
    calc.add_argument("--offline", action="store_true")
    calc.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        print(f"로컬 화면: http://127.0.0.1:{args.port}")
        uvicorn.run("gems_research.server:app", host="127.0.0.1", port=args.port)
        return
    if sum([bool(args.demo), bool(args.input), bool(args.symbol)]) != 1:
        parser.error("--demo, --input FILE, 종목코드 중 하나를 선택하세요.")
    try:
        data = demo_input() if args.demo else AnalysisInput.model_validate_json(args.input.read_text(encoding="utf-8")) if args.input else load_company(args.symbol, args.market, args.offline)
        result = analyze(data)
        print(json.dumps(dict(input=data.model_dump(mode="json"), result=result), ensure_ascii=False, indent=2) if args.format == "json" else markdown_report(data, result))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        parser.exit(1, "분석 실패: " + str(exc) + "\n")
