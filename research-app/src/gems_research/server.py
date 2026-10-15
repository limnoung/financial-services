from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import storage
from .data import demo_input, load_company
from .models import AnalysisInput, LoadInput
from .reports import gemini_prompt, markdown_report
from .rubric import catalog
from .review import financial_review, workflow_text
from .scoring import analyze

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Gems Research", docs_url="/api/docs")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/rubric")
def rubric():
    return catalog()


@app.get("/api/demo")
def demo():
    return demo_input().model_dump(mode="json")


@app.post("/api/company")
def company(request: LoadInput):
    try:
        return load_company(request.symbol, request.market, request.offline).model_dump(mode="json")
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        raise HTTPException(422, detail="데이터를 가져오지 못했습니다. " + str(exc)[:500]) from exc


@app.post("/api/analyze")
def calculate(data: AnalysisInput):
    result = analyze(data)
    return dict(input=data.model_dump(mode="json"), result=result, review=financial_review(data, result), report=markdown_report(data, result), gems_prompt=gemini_prompt(data, result))


@app.post("/api/save")
def save(data: AnalysisInput):
    result = analyze(data)
    key = storage.save(data.model_dump(mode="json"), result)
    return dict(id=key, result=result)


@app.get("/api/history")
def history():
    return storage.history()


@app.get("/api/history/{key}")
def snapshot(key: str):
    record = storage.get(key)
    if record is None:
        raise HTTPException(404, "저장 기록이 없습니다.")
    return record


@app.post("/api/review")
def review(data: AnalysisInput):
    return financial_review(data)


@app.get("/api/workflows/{key}", response_class=PlainTextResponse)
def workflow(key: str):
    try:
        return workflow_text(key)
    except KeyError as exc:
        raise HTTPException(404, "알 수 없는 검토 절차입니다.") from exc
