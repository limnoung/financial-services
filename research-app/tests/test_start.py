import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


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
    monkeypatch.setattr(module.subprocess, "call", lambda argv, **kwargs: calls.append(argv) or 0)
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


@pytest.mark.parametrize("failure", ["exit", "missing_base", "timeout"])
def test_broken_venv_is_preserved_and_rebuilt(tmp_path, monkeypatch, failure):
    module = launcher()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    old_environment = tmp_path / ".venv"
    python = old_environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    (old_environment / "preserve.txt").write_text("old environment")
    (old_environment / ".gems-bootstrap.sha256").write_text("outdated marker")
    monkeypatch.setattr(module, "__file__", str(tmp_path / "start.py"))
    monkeypatch.setattr(module.sys, "argv", ["start.py", "--no-browser"])
    monkeypatch.setenv("PYTHONHOME", "removed-python")
    monkeypatch.setenv("PYTHONPATH", "unrelated-site-packages")
    recreated = []
    calls = []

    def create(path, **kwargs):
        recreated.append(path)
        assert not path.exists()
        python.parent.mkdir(parents=True)
        python.touch()

    def run(argv, **kwargs):
        assert "PYTHONHOME" not in kwargs["env"]
        assert "PYTHONPATH" not in kwargs["env"]
        calls.append(argv)
        if "-c" in argv:
            if failure == "missing_base":
                raise OSError("No Python at removed base install")
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, 10)
            return SimpleNamespace(returncode=103)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.venv, "create", create)
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.subprocess, "call", lambda argv, **kwargs: 0)
    assert module.main() == 0
    assert recreated == [old_environment]
    backups = list(tmp_path.glob(".venv.broken-*"))
    assert len(backups) == 1
    assert (backups[0] / "preserve.txt").read_text() == "old environment"
    assert not (old_environment / "preserve.txt").exists()
    assert any("install" in argv for argv in calls)
    assert os.environ["PYTHONHOME"] == "removed-python"  # parent settings untouched


def test_windows_launcher_sources_are_ascii():
    root = Path(__file__).resolve().parents[1]
    (root / "start.ps1").read_bytes().decode("ascii")
    (root / "start.cmd").read_bytes().decode("ascii")


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows PowerShell and cmd.exe")
def test_windows_cmd_selects_working_python_with_stale_override(tmp_path):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "research app with spaces"
    project.mkdir()
    for name in ("start.cmd", "start.ps1"):
        shutil.copyfile(root / name, project / name)
    child_env = os.environ.copy()
    child_env["GEMS_PYTHON"] = str(tmp_path / "deleted Python3.13" / "python.exe")
    child_env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + child_env["PATH"]
    result = subprocess.run(["cmd.exe", "/d", "/c", "start.cmd", "--diagnose-python"], cwd=project,
                            env=child_env, capture_output=True, timeout=60)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert b"Selected Python:" in result.stdout
    assert not (project / ".venv").exists()  # diagnosis does not install anything
