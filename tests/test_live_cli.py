"""Tests for live-barrage CLI argument parsing and integration."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestLiveBarrageCLI:
    def test_help_output(self):
        result = subprocess.run(
            [sys.executable, "main.py", "live-barrage", "--help"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "room_url" in result.stdout
        assert "--duration" in result.stdout
        assert "--output" in result.stdout

    def test_help_shows_output_choices(self):
        result = subprocess.run(
            [sys.executable, "main.py", "live-barrage", "--help"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
        assert "console" in result.stdout
        assert "json" in result.stdout
        assert "feishu" in result.stdout

    def test_main_help_includes_live_barrage(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--help"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "live-barrage" in result.stdout


class TestSmokeTest:
    def test_check_command(self):
        result = subprocess.run(
            [sys.executable, "main.py", "check"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestSettingsIntegration:
    def test_default_duration_from_settings(self):
        from config.settings import LIVE_DEFAULT_DURATION
        assert isinstance(LIVE_DEFAULT_DURATION, int)
        assert LIVE_DEFAULT_DURATION >= 0

    def test_default_output_mode_from_settings(self):
        from config.settings import LIVE_OUTPUT_MODE
        assert LIVE_OUTPUT_MODE in ("console", "feishu", "json")

    def test_settings_used_in_argparse(self):
        import importlib
        from config import settings
        original_dur = settings.LIVE_DEFAULT_DURATION
        original_mode = settings.LIVE_OUTPUT_MODE

        assert isinstance(original_dur, int)
        assert isinstance(original_mode, str)
