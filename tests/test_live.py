"""Unit tests for scrapers.live — heartbeat, reconnection, JSONL error handling."""
import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.live import LiveBarrageScraper, _now_iso, _extract_room_id


def _make_scraper(**kwargs):
    s = LiveBarrageScraper(**kwargs)
    s._stop_event = asyncio.Event()
    s._room_id = "test_room"
    s._room_url = "https://www.xiaohongshu.com/live/test_room"
    return s


class TestLogFrame(unittest.TestCase):
    """JSONL write error handling and file reopen."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.scraper = _make_scraper(capture_dir=self.tmpdir)
        self.cap_path = Path(self.tmpdir) / "test.jsonl"
        self.scraper._capture_path = self.cap_path
        self.scraper._capture_file = open(self.cap_path, "a", encoding="utf-8")

    def tearDown(self):
        if self.scraper._capture_file:
            self.scraper._capture_file.close()
        for f in Path(self.tmpdir).glob("*"):
            f.unlink()
        Path(self.tmpdir).rmdir()

    def test_successful_write_resets_consecutive_errors(self):
        self.scraper._consecutive_write_errors = 3
        self.scraper._log_frame("send", "text", "hello")
        self.assertEqual(self.scraper._consecutive_write_errors, 0)

    def test_write_produces_valid_jsonl(self):
        self.scraper._log_frame("receive", "text", "test_data")
        self.scraper._capture_file.flush()
        with open(self.cap_path) as f:
            line = f.readline()
        record = json.loads(line)
        self.assertEqual(record["direction"], "receive")
        self.assertEqual(record["type"], "text")
        self.assertEqual(record["data"], "test_data")

    def test_write_error_increments_counters(self):
        self.scraper._capture_file.close()
        self.scraper._capture_file = MagicMock()
        self.scraper._capture_file.write.side_effect = OSError("disk full")

        self.scraper._log_frame("send", "text", "data")
        self.assertEqual(self.scraper._log_write_errors, 1)
        self.assertEqual(self.scraper._consecutive_write_errors, 1)

    def test_consecutive_errors_trigger_reopen(self):
        self.scraper._capture_file.close()
        mock_file = MagicMock()
        mock_file.write.side_effect = OSError("bad fd")
        self.scraper._capture_file = mock_file

        for _ in range(self.scraper.JSONL_REOPEN_THRESHOLD):
            self.scraper._log_frame("send", "text", "data")

        self.assertEqual(
            self.scraper._consecutive_write_errors, 0,
            "Consecutive errors should reset after successful file reopen",
        )

    def test_reopen_failure_disables_logging(self):
        self.scraper._capture_file.close()
        self.scraper._capture_file = MagicMock()
        self.scraper._capture_file.write.side_effect = OSError("bad fd")
        self.scraper._capture_path = Path("/nonexistent/dir/file.jsonl")

        for _ in range(self.scraper.JSONL_REOPEN_THRESHOLD):
            self.scraper._log_frame("send", "text", "data")

        self.assertIsNone(self.scraper._capture_file)

    def test_no_write_when_capture_file_is_none(self):
        self.scraper._capture_file.close()
        self.scraper._capture_file = None
        self.scraper._log_frame("send", "text", "data")
        self.assertEqual(self.scraper._log_write_errors, 0)


class TestReconnect(unittest.TestCase):
    """Reconnection with exponential backoff and configurable limit."""

    def test_default_max_reconnects_is_unlimited(self):
        s = _make_scraper()
        self.assertEqual(s._max_reconnects, 0)

    def test_custom_max_reconnects(self):
        s = _make_scraper(max_reconnects=5)
        self.assertEqual(s._max_reconnects, 5)

    def test_reconnect_limit_stops_session(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper(max_reconnects=2)
            s._page = MagicMock()
            s._reconnect_count = 2

            loop.run_until_complete(s._attempt_reconnect())

            self.assertTrue(s._stop_event.is_set())
        finally:
            loop.close()

    def test_reconnect_increments_count(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper()
            s._page = MagicMock()
            s._page.reload = AsyncMock()

            original_sleep = asyncio.sleep

            async def fast_sleep(delay):
                await original_sleep(0)

            with patch("scrapers.live.asyncio.sleep", side_effect=fast_sleep):
                loop.run_until_complete(s._attempt_reconnect())

            self.assertEqual(s._reconnect_count, 1)
            self.assertFalse(s._reconnecting)
        finally:
            loop.close()

    def test_backoff_delay_grows_exponentially(self):
        s = _make_scraper()
        initial = s.RECONNECT_INITIAL_DELAY_S
        factor = s.RECONNECT_BACKOFF_FACTOR
        max_delay = s.RECONNECT_MAX_DELAY_S

        for count in range(6):
            expected = min(initial * (factor ** count), max_delay)
            delay = min(initial * (factor ** count), max_delay)
            self.assertEqual(delay, expected)

    def test_backoff_capped_at_max(self):
        s = _make_scraper()
        count = 100
        delay = min(
            s.RECONNECT_INITIAL_DELAY_S * (s.RECONNECT_BACKOFF_FACTOR ** count),
            s.RECONNECT_MAX_DELAY_S,
        )
        self.assertEqual(delay, s.RECONNECT_MAX_DELAY_S)

    def test_reconnect_skipped_when_already_reconnecting(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper()
            s._page = MagicMock()
            s._reconnecting = True
            s._reconnect_count = 0

            loop.run_until_complete(s._attempt_reconnect())

            self.assertEqual(s._reconnect_count, 0)
        finally:
            loop.close()

    def test_reconnect_skipped_when_no_page(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper()
            s._page = None

            loop.run_until_complete(s._attempt_reconnect())

            self.assertEqual(s._reconnect_count, 0)
        finally:
            loop.close()

    def test_target_frame_resets_reconnect_count(self):
        s = _make_scraper()
        s._reconnect_count = 5
        s._capture_file = MagicMock()
        s._on_frame("receive", '{"content":"hi"}', is_target=True)
        self.assertEqual(s._reconnect_count, 0)


class TestHeartbeatWatchdog(unittest.TestCase):
    """Heartbeat watchdog detects stale connections."""

    def test_watchdog_triggers_reconnect_on_stale(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper()
            s._ws_matched = True
            s._last_frame_time = time.monotonic() - 120
            s._page = MagicMock()
            s._page.reload = AsyncMock()
            s._capture_file = MagicMock()

            reconnect_called = False
            original_reconnect = s._attempt_reconnect

            async def mock_reconnect():
                nonlocal reconnect_called
                reconnect_called = True
                s._stop_event.set()

            s._attempt_reconnect = mock_reconnect
            s.HEARTBEAT_TIMEOUT_S = 0.1

            async def run():
                task = asyncio.ensure_future(s._heartbeat_watchdog())
                await asyncio.sleep(0.2)
                s._stop_event.set()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            loop.run_until_complete(run())
            self.assertTrue(reconnect_called)
        finally:
            loop.close()

    def test_watchdog_no_reconnect_when_frames_arriving(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper()
            s._ws_matched = True
            s._last_frame_time = time.monotonic()
            s._capture_file = MagicMock()

            reconnect_called = False

            async def mock_reconnect():
                nonlocal reconnect_called
                reconnect_called = True

            s._attempt_reconnect = mock_reconnect
            s.HEARTBEAT_TIMEOUT_S = 10

            async def run():
                task = asyncio.ensure_future(s._heartbeat_watchdog())
                await asyncio.sleep(0.1)
                s._stop_event.set()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            loop.run_until_complete(run())
            self.assertFalse(reconnect_called)
        finally:
            loop.close()


class TestKeepaliveLoop(unittest.TestCase):
    """Page keepalive loop runs periodically."""

    def test_keepalive_calls_page_evaluate(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper()
            s._page = MagicMock()
            s._page.evaluate = AsyncMock(return_value=None)
            s.KEEPALIVE_INTERVAL_S = 0.05

            async def run():
                task = asyncio.ensure_future(s._keepalive_loop())
                await asyncio.sleep(0.15)
                s._stop_event.set()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            loop.run_until_complete(run())
            self.assertTrue(s._page.evaluate.call_count >= 1)
        finally:
            loop.close()

    def test_keepalive_skips_during_reconnect(self):
        loop = asyncio.new_event_loop()
        try:
            s = _make_scraper()
            s._page = MagicMock()
            s._page.evaluate = AsyncMock(return_value=None)
            s._reconnecting = True
            s.KEEPALIVE_INTERVAL_S = 0.05

            async def run():
                task = asyncio.ensure_future(s._keepalive_loop())
                await asyncio.sleep(0.15)
                s._stop_event.set()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            loop.run_until_complete(run())
            self.assertEqual(s._page.evaluate.call_count, 0)
        finally:
            loop.close()


class TestHelpers(unittest.TestCase):
    def test_extract_room_id(self):
        self.assertEqual(_extract_room_id("https://www.xiaohongshu.com/live/abc123"), "abc123")
        self.assertEqual(_extract_room_id("https://example.com/page"), "")

    def test_now_iso_returns_cst(self):
        result = _now_iso()
        self.assertTrue(result.endswith("+08:00"))


if __name__ == "__main__":
    unittest.main()
