import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def launcher():
    path = Path(__file__).resolve().parents[1] / "start.py"
    spec = importlib.util.spec_from_file_location("research_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_installs_once_and_passes_port_without_shell(tmp_path, monkeypatch):
    module = launcher()
    project = tmp_path / "research app with spaces"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='test'\n")
    monkeypatch.setattr(module, "__file__", str(project / "start.py"))
    monkeypatch.setattr(module.sys, "argv", ["start.py", "--no-browser", "--port", "9000"])
    calls = []

    def create(path, **kwargs):
        python = path / ("Scripts/python.exe" if module.os.name == "nt" else "bin/python")
        python.parent.mkdir(parents=True)
        python.touch()

    monkeypatch.setattr(module.venv, "create", create)
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(module.subprocess, "call", lambda argv: calls.append(argv) or 0)
    assert module.main() == 0
    installs = [args for args in calls if "install" in args]
    assert len(installs) == 1
    assert installs[0][-1] == str(project) + "[data]"
    assert calls[-1][-3:] == ["serve", "--port", "9000"]
    calls.clear()
    assert module.main() == 0
    assert not any("install" in args for args in calls)
    assert (project / ".venv/.gems-bootstrap.sha256").read_text() == hashlib.sha256((project / "pyproject.toml").read_bytes()).hexdigest()


def test_launcher_rejects_unsupported_python_before_install(monkeypatch):
    module = launcher()
    monkeypatch.setattr(module.sys, "argv", ["start.py", "--no-browser"])
    monkeypatch.setattr(module.sys, "version_info", (3, 11))
    assert module.main() == 1
