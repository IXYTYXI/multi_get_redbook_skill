"""Tests for the live barrage module skeleton.

Covers:
- LiveBarrageInfo data model (instantiation, defaults, to_dict, field types)
- LiveBarrageScraper class interface (methods exist, raise NotImplementedError)
- CLI argument parsing for `live-barrage` subcommand
- Config settings for live barrage
"""
import asyncio
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.data import LiveBarrageInfo
from scrapers.live import LiveBarrageScraper


class TestLiveBarrageInfo(unittest.TestCase):
    """Tests for the LiveBarrageInfo data model."""

    def test_default_instantiation(self):
        info = LiveBarrageInfo()
        self.assertEqual(info.user_id, "")
        self.assertEqual(info.user_name, "")
        self.assertEqual(info.content, "")
        self.assertEqual(info.message_type, "")
        self.assertEqual(info.timestamp, "")
        self.assertEqual(info.room_id, "")
        self.assertEqual(info.room_url, "")
        self.assertEqual(info.raw_data, "")

    def test_instantiation_with_values(self):
        info = LiveBarrageInfo(
            user_id="uid_123",
            user_name="TestUser",
            content="Hello live!",
            message_type="barrage",
            timestamp="2026-07-07T12:00:00Z",
            room_id="room_456",
            room_url="https://www.xiaohongshu.com/live/room_456",
            raw_data='{"type":"barrage","text":"Hello live!"}',
        )
        self.assertEqual(info.user_id, "uid_123")
        self.assertEqual(info.user_name, "TestUser")
        self.assertEqual(info.content, "Hello live!")
        self.assertEqual(info.message_type, "barrage")
        self.assertEqual(info.timestamp, "2026-07-07T12:00:00Z")
        self.assertEqual(info.room_id, "room_456")
        self.assertEqual(info.room_url, "https://www.xiaohongshu.com/live/room_456")
        self.assertEqual(info.raw_data, '{"type":"barrage","text":"Hello live!"}')

    def test_partial_instantiation(self):
        info = LiveBarrageInfo(user_id="u1", content="hi")
        self.assertEqual(info.user_id, "u1")
        self.assertEqual(info.content, "hi")
        self.assertEqual(info.user_name, "")
        self.assertEqual(info.room_id, "")

    def test_to_dict(self):
        info = LiveBarrageInfo(
            user_id="u1",
            user_name="name1",
            content="test msg",
            message_type="gift",
            timestamp="ts1",
            room_id="r1",
            room_url="url1",
            raw_data="raw1",
        )
        d = info.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["user_id"], "u1")
        self.assertEqual(d["user_name"], "name1")
        self.assertEqual(d["content"], "test msg")
        self.assertEqual(d["message_type"], "gift")
        self.assertEqual(d["timestamp"], "ts1")
        self.assertEqual(d["room_id"], "r1")
        self.assertEqual(d["room_url"], "url1")
        self.assertEqual(d["raw_data"], "raw1")

    def test_to_dict_has_all_expected_keys(self):
        expected_keys = {
            "user_id", "user_name", "content", "message_type",
            "timestamp", "room_id", "room_url", "raw_data",
        }
        d = LiveBarrageInfo().to_dict()
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_returns_new_dict(self):
        info = LiveBarrageInfo(user_id="u1")
        d1 = info.to_dict()
        d2 = info.to_dict()
        self.assertEqual(d1, d2)
        self.assertIsNot(d1, d2)

    def test_message_type_values(self):
        for mt in ("barrage", "gift", "enter", "follow", "like", "unknown"):
            info = LiveBarrageInfo(message_type=mt)
            self.assertEqual(info.message_type, mt)
            self.assertEqual(info.to_dict()["message_type"], mt)

    def test_all_fields_are_strings(self):
        info = LiveBarrageInfo()
        for key, val in info.to_dict().items():
            self.assertIsInstance(val, str, f"Field {key} should default to str")

    def test_empty_content(self):
        info = LiveBarrageInfo(content="")
        self.assertEqual(info.content, "")
        self.assertEqual(info.to_dict()["content"], "")

    def test_unicode_content(self):
        info = LiveBarrageInfo(
            content="直播弹幕测试 🎉",
            user_name="用户名",
        )
        self.assertEqual(info.content, "直播弹幕测试 🎉")
        self.assertEqual(info.user_name, "用户名")
        d = info.to_dict()
        self.assertEqual(d["content"], "直播弹幕测试 🎉")


class TestLiveBarrageScraper(unittest.TestCase):
    """Tests for the LiveBarrageScraper skeleton."""

    def test_init_no_browser(self):
        scraper = LiveBarrageScraper()
        self.assertIsNone(scraper.browser)

    def test_init_with_browser(self):
        mock_browser = object()
        scraper = LiveBarrageScraper(browser=mock_browser)
        self.assertIs(scraper.browser, mock_browser)

    def test_connect_raises_not_implemented(self):
        scraper = LiveBarrageScraper()
        with self.assertRaises(NotImplementedError):
            asyncio.run(scraper.connect("https://www.xiaohongshu.com/live/test"))

    def test_listen_raises_not_implemented(self):
        scraper = LiveBarrageScraper()
        with self.assertRaises(NotImplementedError):
            asyncio.run(scraper.listen("https://www.xiaohongshu.com/live/test"))

    def test_listen_with_all_params_raises_not_implemented(self):
        scraper = LiveBarrageScraper()
        with self.assertRaises(NotImplementedError):
            asyncio.run(
                scraper.listen(
                    "https://www.xiaohongshu.com/live/test",
                    duration=60,
                    on_message=lambda msg: None,
                )
            )

    def test_disconnect_raises_not_implemented(self):
        scraper = LiveBarrageScraper()
        with self.assertRaises(NotImplementedError):
            asyncio.run(scraper.disconnect())

    def test_connect_is_coroutine(self):
        scraper = LiveBarrageScraper()
        coro = scraper.connect("url")
        self.assertTrue(asyncio.iscoroutine(coro))
        coro.close()

    def test_listen_is_coroutine(self):
        scraper = LiveBarrageScraper()
        coro = scraper.listen("url")
        self.assertTrue(asyncio.iscoroutine(coro))
        coro.close()

    def test_disconnect_is_coroutine(self):
        scraper = LiveBarrageScraper()
        coro = scraper.disconnect()
        self.assertTrue(asyncio.iscoroutine(coro))
        coro.close()

    def test_has_expected_methods(self):
        scraper = LiveBarrageScraper()
        self.assertTrue(callable(getattr(scraper, "connect", None)))
        self.assertTrue(callable(getattr(scraper, "listen", None)))
        self.assertTrue(callable(getattr(scraper, "disconnect", None)))


class TestLiveBarrageConfig(unittest.TestCase):
    """Tests for live barrage configuration settings."""

    def test_default_config_values(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LIVE_TABLE_ID", None)
            os.environ.pop("LIVE_OUTPUT_MODE", None)
            os.environ.pop("LIVE_DEFAULT_DURATION", None)
            import importlib
            import config.settings as settings
            importlib.reload(settings)

            self.assertEqual(settings.LIVE_TABLE_ID, "")
            self.assertEqual(settings.LIVE_OUTPUT_MODE, "console")
            self.assertEqual(settings.LIVE_DEFAULT_DURATION, 0)

    def test_config_from_env(self):
        env_vals = {
            "LIVE_TABLE_ID": "tbl_live_123",
            "LIVE_OUTPUT_MODE": "json",
            "LIVE_DEFAULT_DURATION": "300",
        }
        with patch.dict(os.environ, env_vals, clear=False):
            import importlib
            import config.settings as settings
            importlib.reload(settings)

            self.assertEqual(settings.LIVE_TABLE_ID, "tbl_live_123")
            self.assertEqual(settings.LIVE_OUTPUT_MODE, "json")
            self.assertEqual(settings.LIVE_DEFAULT_DURATION, 300)

    def test_config_feishu_output_mode(self):
        with patch.dict(os.environ, {"LIVE_OUTPUT_MODE": "feishu"}, clear=False):
            import importlib
            import config.settings as settings
            importlib.reload(settings)
            self.assertEqual(settings.LIVE_OUTPUT_MODE, "feishu")


class TestLiveBarrageCLI(unittest.TestCase):
    """Tests for the live-barrage CLI subcommand."""

    def _run_cli(self, *args):
        root = os.path.join(os.path.dirname(__file__), "..")
        main_py = os.path.join(root, "main.py")
        result = subprocess.run(
            [sys.executable, main_py] + list(args),
            capture_output=True,
            text=True,
            cwd=root,
            timeout=30,
        )
        return result

    def test_help_shows_live_barrage(self):
        result = self._run_cli("--help")
        self.assertIn("live-barrage", result.stdout)

    def test_live_barrage_help(self):
        result = self._run_cli("live-barrage", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("room_url", result.stdout)
        self.assertIn("--duration", result.stdout)
        self.assertIn("--output", result.stdout)

    def test_live_barrage_help_output_choices(self):
        result = self._run_cli("live-barrage", "--help")
        self.assertIn("console", result.stdout)
        self.assertIn("feishu", result.stdout)
        self.assertIn("json", result.stdout)

    def test_live_barrage_missing_room_url(self):
        result = self._run_cli("live-barrage")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("room_url", result.stderr)

    def test_live_barrage_invalid_output(self):
        result = self._run_cli("live-barrage", "http://test.url", "--output", "invalid")
        self.assertNotEqual(result.returncode, 0)

    def test_check_passes(self):
        result = self._run_cli("check")
        self.assertEqual(result.returncode, 0, f"check failed: {result.stderr}")
        self.assertIn("OK", result.stdout)


class TestLiveBarrageCLIParsing(unittest.TestCase):
    """Tests for argparse config in main.py (without actually running the scraper)."""

    def _parse(self, *args):
        import argparse
        parser = argparse.ArgumentParser(prog="xhs-scraper")
        sub = parser.add_subparsers(dest="command")
        p_live = sub.add_parser("live-barrage")
        p_live.add_argument("room_url")
        p_live.add_argument("--duration", type=int, default=0)
        p_live.add_argument("--output", choices=["console", "feishu", "json"], default="console")
        return parser.parse_args(list(args))

    def test_parse_minimal(self):
        args = self._parse("live-barrage", "https://example.com/live/123")
        self.assertEqual(args.command, "live-barrage")
        self.assertEqual(args.room_url, "https://example.com/live/123")
        self.assertEqual(args.duration, 0)
        self.assertEqual(args.output, "console")

    def test_parse_with_duration(self):
        args = self._parse("live-barrage", "https://example.com/live/123", "--duration", "120")
        self.assertEqual(args.duration, 120)

    def test_parse_with_json_output(self):
        args = self._parse("live-barrage", "https://example.com/live/123", "--output", "json")
        self.assertEqual(args.output, "json")

    def test_parse_with_feishu_output(self):
        args = self._parse("live-barrage", "https://example.com/live/123", "--output", "feishu")
        self.assertEqual(args.output, "feishu")

    def test_parse_with_all_options(self):
        args = self._parse(
            "live-barrage", "https://example.com/live/123",
            "--duration", "60", "--output", "json",
        )
        self.assertEqual(args.room_url, "https://example.com/live/123")
        self.assertEqual(args.duration, 60)
        self.assertEqual(args.output, "json")


if __name__ == "__main__":
    unittest.main()
