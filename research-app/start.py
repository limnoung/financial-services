"""Install the local app once, then launch its native DartLab workspace."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
import venv
import webbrowser


def python_works(python: Path, child_env: dict[str, str]) -> bool:
    if not python.is_file():
        return False
    try:
        return subprocess.run(
            [str(python), "-I", "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=10, env=child_env,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="DartLab 통합 리서치 시작")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        print("Python 3.12 이상을 설치한 뒤 다시 실행하세요.")
        return 1
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    child_env = os.environ.copy()
    # A global setting for a removed Python must not contaminate this venv.
    child_env.pop("PYTHONHOME", None)
    child_env.pop("PYTHONPATH", None)
    if not python_works(python, child_env):
        if environment.exists():
            backup = root / (".venv.broken-" + uuid.uuid4().hex[:12])
            environment.rename(backup)
            print(f"실행할 수 없는 기존 가상환경을 보존했습니다: {backup.name}", flush=True)
        print("통합 프로그램의 가상환경을 준비합니다.", flush=True)
        venv.create(environment, with_pip=True)
    if subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True, env=child_env).returncode:
        subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], check=True, env=child_env)
    digest = hashlib.sha256((root / "pyproject.toml").read_bytes()).hexdigest()
    marker = environment / ".gems-bootstrap.sha256"
    if not marker.is_file() or marker.read_text() != digest:
        print("DartLab과 리서치 기능을 설치합니다. 첫 실행에는 시간이 걸릴 수 있습니다.", flush=True)
        subprocess.run([str(python), "-X", "utf8", "-m", "pip", "install", "-e", str(root) + "[data]"], check=True, env=child_env)
        marker.write_text(digest)
    url = f"http://127.0.0.1:{args.port}"
    print(f"DartLab 통합 화면: {url}\n종료: Ctrl+C", flush=True)

    if not args.no_browser:
        def open_when_ready():
            # Poll a lightweight local document, never the data or AI endpoints.
            for _ in range(60):
                threading.Event().wait(0.5)
                try:
                    with urllib.request.urlopen(url + "/_gems-extension/bridge.js", timeout=1) as response:
                        if response.status == 200:
                            webbrowser.open(url)
                            return
                except (OSError, urllib.error.URLError):
                    continue
            print(f"브라우저에서 직접 열어 주세요: {url}", flush=True)
        threading.Thread(target=open_when_ready, daemon=True).start()
    return subprocess.call([str(python), "-X", "utf8", "-m", "gems_research", "serve", "--port", str(args.port)], env=child_env)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"시작 실패: {exc}", file=sys.stderr)
        raise SystemExit(1)
