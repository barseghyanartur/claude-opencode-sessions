"""The shell launcher used by the Claude Code plugin hook."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "opencode-sessions"

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell launcher"),
    pytest.mark.skipif(not LAUNCHER.exists(), reason="not running from a checkout"),
]


def test_launcher_runs_bundled_package():
    result = subprocess.run(
        ["sh", str(LAUNCHER), "--version"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "OCS_PYTHON": sys.executable},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("claude-opencode-sessions ")


def test_launcher_reports_missing_python(tmp_path: Path):
    sh = shutil.which("sh")
    assert sh
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for tool in ("dirname", "sh"):
        found = shutil.which(tool)
        if found:
            (fake_bin / tool).symlink_to(found)
    result = subprocess.run(
        [sh, str(LAUNCHER), "list"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": str(fake_bin)},
    )
    assert result.returncode == 5
    assert "Python >= 3.10 is required" in result.stderr
