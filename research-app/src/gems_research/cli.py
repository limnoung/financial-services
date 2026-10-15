from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import demo_input, load_company
from .models import AnalysisInput
from .reports import markdown_report
from .scoring import analyze


def main():
    parser = argparse.ArgumentParser(description="DartLab + financial-services + Gems 통합 리서치")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="DartLab 기본 화면과 Gems 통합 실행")
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--standalone", action="store_true", help="기존 독립 Gems 화면만 실행")
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
        if args.standalone:
            uvicorn.run("gems_research.server:app", host="127.0.0.1", port=args.port)
        else:
            try:
                from .native import create_app
                app = create_app()
            except (ImportError, RuntimeError) as exc:
                parser.exit(1, f"통합 실행 실패: {exc}\n설치: python -m pip install -e \".[data]\"\n")
            uvicorn.run(app, host="127.0.0.1", port=args.port)
        return
    if sum([bool(args.demo), bool(args.input), bool(args.symbol)]) != 1:
        parser.error("--demo, --input FILE, 종목코드 중 하나를 선택하세요.")
    try:
        data = demo_input() if args.demo else AnalysisInput.model_validate_json(args.input.read_text(encoding="utf-8")) if args.input else load_company(args.symbol, args.market, args.offline)
        result = analyze(data)
        print(json.dumps(dict(input=data.model_dump(mode="json"), result=result), ensure_ascii=False, indent=2) if args.format == "json" else markdown_report(data, result))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        parser.exit(1, "분석 실패: " + str(exc) + "\n")
