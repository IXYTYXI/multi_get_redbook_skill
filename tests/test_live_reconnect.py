"""Tests for WebSocket reconnection and connection management logic."""
import pytest
from scrapers.live import LiveBarrageScraper


class TestWsConnectionTracking:
    def test_connections_list_starts_empty(self):
        s = LiveBarrageScraper()
        assert s._ws_connections == []

    def test_frame_count_starts_zero(self):
        s = LiveBarrageScraper()
        assert s._ws_frame_count == 0

    def test_last_frame_time_starts_zero(self):
        s = LiveBarrageScraper()
        assert s._last_frame_time == 0.0


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_sets_running_false(self):
        s = LiveBarrageScraper()
        s._running = True
        await s.disconnect()
        assert s._running is False

    @pytest.mark.asyncio
    async def test_disconnect_without_capture(self):
        s = LiveBarrageScraper()
        s._capture_file = None
        await s.disconnect()


class TestConnectRequiresBrowser:
    @pytest.mark.asyncio
    async def test_connect_raises_without_browser(self):
        s = LiveBarrageScraper()
        with pytest.raises(RuntimeError, match="requires a browser"):
            await s.connect("https://www.xiaohongshu.com/live/test")

    @pytest.mark.asyncio
    async def test_listen_raises_without_browser(self):
        s = LiveBarrageScraper()
        with pytest.raises(RuntimeError, match="requires a browser"):
            await s.listen("https://www.xiaohongshu.com/live/test")
