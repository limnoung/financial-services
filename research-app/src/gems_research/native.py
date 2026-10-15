"""Serve DartLab's installed UI and APIs with a small research drawer.

The upstream UI bundle and package files are never modified. Namespace our API
under /gems so DartLab's routes, SSE streams and assets retain their contracts.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from importlib.metadata import version
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .data import configure_data_dir
from .server import app as gems_app
from . import __version__

STATIC = Path(__file__).parent / "native_static"
INJECTION = f'<link rel="stylesheet" href="/_gems-extension/bridge.css?v={__version__}"><script defer src="/_gems-extension/bridge.js?v={__version__}"></script><script defer src="/_gems-extension/codex.js?v={__version__}"></script>'


def create_app() -> FastAPI:
    if version("dartlab") != "0.12.0":
        raise RuntimeError("통합 화면은 dartlab==0.12.0 기준입니다. 지정 버전을 설치하세요.")
    configure_data_dir()
    from dartlab.server import app as dartlab_app
    from dartlab.server._ui_path import resolveUiBuildDir
    from .codex_models import install_codex_model_bridge

    install_codex_model_bridge()

    index = resolveUiBuildDir() / "index.html"
    if not index.is_file():
        raise RuntimeError("DartLab UI 배포 파일이 없습니다. dartlab==0.12.0을 다시 설치하세요.")

    @asynccontextmanager
    async def lifespan(_):
        # Mounted applications do not receive ASGI lifespan events themselves.
        async with dartlab_app.router.lifespan_context(dartlab_app):
            yield

    app = FastAPI(title="DartLab Research", lifespan=lifespan, docs_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    from .codex_api import router as codex_router
    app.include_router(codex_router)

    @app.get("/_gems-extension/status")
    def integration_status():
        from fastapi.responses import JSONResponse
        return JSONResponse({"app": "gems-research", "version": __version__,
                             "launch_id": os.environ.get("GEMS_LAUNCH_ID")},
                            headers={"Cache-Control": "no-store"})

    app.mount("/gems", gems_app)
    app.mount("/_gems-extension", StaticFiles(directory=STATIC))

    async def native_page():
        # Only HTML entry pages are augmented. All original assets and API
        # responses, including streaming responses, go straight to DartLab.
        html = index.read_text(encoding="utf-8").replace("</head>", INJECTION + "</head>", 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"})

    for path in ("/", "/terminal/{code}", "/analysis/{code}", "/analysis/{code}/viewer", "/chat", "/settings", "/ask", "/settings/{path:path}", "/chat/{path:path}", "/ask/{path:path}"):
        app.add_api_route(path, native_page, methods=["GET"], include_in_schema=False)
    app.mount("/", dartlab_app)
    return app
