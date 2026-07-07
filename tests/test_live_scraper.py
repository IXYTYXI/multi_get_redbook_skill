"""Tests for LiveBarrageScraper parsing and helper methods."""
import base64
import gzip
import json
import os
import tempfile
from pathlib import Path

import pytest
from scrapers.live import LiveBarrageScraper
from models.data import LiveBarrageInfo


@pytest.fixture
def scraper():
    s = LiveBarrageScraper()
    s._room_id = "test_room"
    s._room_url = "https://www.xiaohongshu.com/live/test_room"
    return s


# ---------------------------------------------------------------
# _extract_room_id
# ---------------------------------------------------------------

class TestExtractRoomId:
    def test_hina_livestream_path(self):
        url = "https://www.xiaohongshu.com/hina/livestream/abc123"
        assert LiveBarrageScraper._extract_room_id(url) == "abc123"

    def test_live_path(self):
        url = "https://www.xiaohongshu.com/live/def456"
        assert LiveBarrageScraper._extract_room_id(url) == "def456"

    def test_query_param(self):
        url = "https://www.xiaohongshu.com/page?room_id=room789&other=1"
        assert LiveBarrageScraper._extract_room_id(url) == "room789"

    def test_trailing_slash(self):
        url = "https://www.xiaohongshu.com/hina/livestream/abc123/"
        assert LiveBarrageScraper._extract_room_id(url) == "abc123"

    def test_alphanumeric_with_underscore(self):
        url = "https://www.xiaohongshu.com/live/room_123_abc"
        assert LiveBarrageScraper._extract_room_id(url) == "room_123_abc"

    def test_fallback_to_last_segment(self):
        url = "https://example.com/some/path/fallback_id"
        assert LiveBarrageScraper._extract_room_id(url) == "fallback_id"

    def test_empty_url(self):
        assert LiveBarrageScraper._extract_room_id("") == ""

    def test_complex_query_string(self):
        url = "https://www.xiaohongshu.com/hina/livestream/abc?foo=bar&baz=1"
        assert LiveBarrageScraper._extract_room_id(url) == "abc"


# ---------------------------------------------------------------
# _try_gzip
# ---------------------------------------------------------------

class TestTryGzip:
    def test_valid_gzip(self):
        original = b"hello world"
        compressed = gzip.compress(original)
        result = LiveBarrageScraper._try_gzip(compressed)
        assert result == original

    def test_gzip_with_prefix(self):
        original = b"test data"
        compressed = gzip.compress(original)
        data = b"\x00\x00\x00" + compressed
        result = LiveBarrageScraper._try_gzip(data)
        assert result == original

    def test_not_gzip(self):
        result = LiveBarrageScraper._try_gzip(b"not gzip data")
        assert result is None

    def test_empty_data(self):
        result = LiveBarrageScraper._try_gzip(b"")
        assert result is None or result == b""

    def test_partial_gzip_header(self):
        result = LiveBarrageScraper._try_gzip(b"\x1f\x8b")
        assert result is None

    def test_gzip_json_payload(self):
        payload = json.dumps({"type": "chat", "content": "你好"}).encode("utf-8")
        compressed = gzip.compress(payload)
        result = LiveBarrageScraper._try_gzip(compressed)
        assert result == payload


# ---------------------------------------------------------------
# _json_to_barrage
# ---------------------------------------------------------------

class TestJsonToBarrage:
    def test_chat_message(self, scraper):
        obj = {
            "type": "chat",
            "content": "Hello everyone",
            "user": {"nickname": "Alice", "id": "u1"},
        }
        msg = scraper._json_to_barrage(obj, "2026-01-01T00:00:00Z", "raw")
        assert msg is not None
        assert msg.message_type == "barrage"
        assert msg.content == "Hello everyone"
        assert msg.user_name == "Alice"
        assert msg.user_id == "u1"

    def test_gift_message(self, scraper):
        obj = {"type": "gift", "content": "Rose x1", "sender": {"name": "Bob", "userId": "u2"}}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "gift"
        assert msg.user_name == "Bob"

    def test_enter_message(self, scraper):
        obj = {"action": "enter", "user": {"nickname": "Charlie", "id": "u3"}}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "enter"
        assert msg.user_name == "Charlie"

    def test_follow_message(self, scraper):
        obj = {"cmd": "follow", "user": {"nickname": "Dave", "id": "u4"}}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "follow"

    def test_like_message(self, scraper):
        obj = {"type": "like", "user": {"nickname": "Eve", "id": "u5"}}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "like"

    def test_barrage_keyword(self, scraper):
        obj = {"type": "barrage", "content": "666"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "barrage"

    def test_comment_keyword(self, scraper):
        obj = {"type": "comment", "text": "nice"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "barrage"
        assert msg.content == "nice"

    def test_danmu_keyword(self, scraper):
        obj = {"msgType": "danmu", "msg": "test"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "barrage"

    def test_member_keyword(self, scraper):
        obj = {"action": "member_join"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.message_type == "enter"

    def test_unknown_type(self, scraper):
        obj = {"type": "heartbeat", "content": "ping"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg is not None
        assert msg.message_type == "unknown"
        assert msg.content == "ping"

    def test_empty_dict_returns_none(self, scraper):
        msg = scraper._json_to_barrage({}, "ts", "raw")
        assert msg is None

    def test_no_useful_info_returns_none(self, scraper):
        obj = {"type": "heartbeat"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg is None

    def test_non_dict_returns_none(self, scraper):
        msg = scraper._json_to_barrage("not a dict", "ts", "raw")
        assert msg is None

    def test_user_info_from_flat_fields(self, scraper):
        obj = {"type": "chat", "content": "hi", "nickname": "Flat", "userId": "f1"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.user_name == "Flat"
        assert msg.user_id == "f1"

    def test_user_info_nested_userinfo(self, scraper):
        obj = {
            "type": "chat", "content": "hi",
            "userInfo": {"nickName": "Nested", "user_id": "n1"},
        }
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.user_name == "Nested"
        assert msg.user_id == "n1"

    def test_content_field_variants(self, scraper):
        for field in ("content", "text", "msg", "message", "body"):
            obj = {"type": "chat", field: "test_value"}
            msg = scraper._json_to_barrage(obj, "ts", "raw")
            assert msg.content == "test_value", f"Failed for field '{field}'"

    def test_content_truncation(self, scraper):
        obj = {"type": "chat", "content": "x" * 1000}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert len(msg.content) == 500

    def test_raw_data_truncation(self, scraper):
        raw = "r" * 2000
        obj = {"type": "chat", "content": "hi"}
        msg = scraper._json_to_barrage(obj, "ts", raw)
        assert len(msg.raw_data) == 1000

    def test_room_id_and_url_set(self, scraper):
        obj = {"type": "chat", "content": "hi"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.room_id == "test_room"
        assert msg.room_url == "https://www.xiaohongshu.com/live/test_room"

    def test_timestamp_propagated(self, scraper):
        obj = {"type": "chat", "content": "hi"}
        msg = scraper._json_to_barrage(obj, "2026-07-07T12:00:00Z", "raw")
        assert msg.timestamp == "2026-07-07T12:00:00Z"

    def test_data_field_as_string_content(self, scraper):
        obj = {"type": "chat", "data": "hello from data field"}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.content == "hello from data field"

    def test_data_field_as_dict_not_used(self, scraper):
        obj = {"type": "chat", "data": {"nested": True}}
        msg = scraper._json_to_barrage(obj, "ts", "raw")
        assert msg.content == ""


# ---------------------------------------------------------------
# _find_utf8_strings
# ---------------------------------------------------------------

class TestFindUtf8Strings:
    def test_simple_ascii(self):
        data = b"hello\x00world"
        result = LiveBarrageScraper._find_utf8_strings(data, min_len=2)
        assert "hello" in result
        assert "world" in result

    def test_cjk_characters(self):
        text = "你好世界"
        data = text.encode("utf-8")
        result = LiveBarrageScraper._find_utf8_strings(data, min_len=2)
        assert any("你好" in s for s in result)

    def test_mixed_binary_and_text(self):
        data = b"\x00\x01\x02hello\x00\x01\x02"
        result = LiveBarrageScraper._find_utf8_strings(data, min_len=2)
        assert "hello" in result

    def test_min_length_filter(self):
        data = b"a\x00bb\x00ccc"
        result = LiveBarrageScraper._find_utf8_strings(data, min_len=3)
        assert "ccc" in result
        assert "a" not in result

    def test_empty_data(self):
        result = LiveBarrageScraper._find_utf8_strings(b"", min_len=2)
        assert result == []

    def test_all_binary(self):
        data = bytes(range(0, 20))
        result = LiveBarrageScraper._find_utf8_strings(data, min_len=2)
        assert len(result) == 0 or all(s.isprintable() for s in result)


# ---------------------------------------------------------------
# _extract_barrage_strings
# ---------------------------------------------------------------

class TestExtractBarrageStrings:
    def test_cjk_pairs(self, scraper):
        name = "用户名"
        content = "弹幕内容"
        data = b"\x00" + name.encode("utf-8") + b"\x00" + content.encode("utf-8") + b"\x00"
        results = scraper._extract_barrage_strings(data, "ts", "raw")
        assert len(results) >= 1
        assert all(isinstance(m, LiveBarrageInfo) for m in results)

    def test_no_cjk_returns_empty(self, scraper):
        data = b"hello world ascii only"
        results = scraper._extract_barrage_strings(data, "ts", "raw")
        assert results == []

    def test_odd_number_of_cjk_strings(self, scraper):
        s1 = "第一"
        s2 = "第二"
        s3 = "第三"
        data = (
            b"\x00" + s1.encode("utf-8") +
            b"\x00" + s2.encode("utf-8") +
            b"\x00" + s3.encode("utf-8") + b"\x00"
        )
        results = scraper._extract_barrage_strings(data, "ts", "raw")
        last = results[-1] if results else None
        if last:
            assert last.message_type == "unknown"

    def test_user_content_swap_heuristic(self, scraper):
        long_name = "这是一个非常长的弹幕内容字符串超过三十个字符"
        short_name = "短名"
        data = (
            b"\x00" + long_name.encode("utf-8") +
            b"\x00" + short_name.encode("utf-8") + b"\x00"
        )
        results = scraper._extract_barrage_strings(data, "ts", "raw")
        if results:
            assert results[0].message_type == "barrage"


# ---------------------------------------------------------------
# _try_parse_frame (text & binary)
# ---------------------------------------------------------------

class TestTryParseFrame:
    def test_text_frame_valid_json(self, scraper):
        payload = json.dumps({"type": "chat", "content": "hi", "user": {"nickname": "A", "id": "1"}})
        msgs = scraper._try_parse_frame(payload)
        assert len(msgs) == 1
        assert msgs[0].content == "hi"

    def test_text_frame_invalid_json(self, scraper):
        msgs = scraper._try_parse_frame("not json")
        assert msgs == []

    def test_binary_frame_gzip_json(self, scraper):
        obj = {"type": "chat", "content": "compressed", "user": {"nickname": "B", "id": "2"}}
        data = gzip.compress(json.dumps(obj).encode("utf-8"))
        msgs = scraper._try_parse_frame(data)
        assert len(msgs) == 1
        assert msgs[0].content == "compressed"

    def test_binary_frame_plain_json(self, scraper):
        obj = {"type": "gift", "content": "Rose"}
        data = json.dumps(obj).encode("utf-8")
        msgs = scraper._try_parse_frame(data)
        assert len(msgs) == 1
        assert msgs[0].message_type == "gift"

    def test_binary_frame_with_cjk(self, scraper):
        data = b"\x00\x01" + "用户".encode("utf-8") + b"\x00" + "弹幕".encode("utf-8") + b"\x00"
        msgs = scraper._try_parse_frame(data)
        # Should extract CJK strings as fallback
        assert isinstance(msgs, list)

    def test_none_payload(self, scraper):
        msgs = scraper._try_parse_frame(None)
        assert msgs == []

    def test_empty_string(self, scraper):
        msgs = scraper._try_parse_frame("")
        assert msgs == []

    def test_empty_bytes(self, scraper):
        msgs = scraper._try_parse_frame(b"")
        assert msgs == []


# ---------------------------------------------------------------
# _record_frame (JSONL capture)
# ---------------------------------------------------------------

class TestRecordFrame:
    def test_record_binary_frame(self, scraper, tmp_path):
        capture = tmp_path / "test.jsonl"
        scraper._capture_file = open(capture, "a", encoding="utf-8")
        scraper._capture_path = capture

        data = b"\x01\x02\x03\x04\x05"
        scraper._record_frame("receive", data, is_binary=True)
        scraper._capture_file.close()

        lines = capture.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["direction"] == "receive"
        assert record["is_binary"] is True
        assert record["size"] == 5
        assert "data_b64" in record
        assert "data_hex_head" in record
        decoded = base64.b64decode(record["data_b64"])
        assert decoded == data

    def test_record_text_frame(self, scraper, tmp_path):
        capture = tmp_path / "test.jsonl"
        scraper._capture_file = open(capture, "a", encoding="utf-8")
        scraper._capture_path = capture

        data = '{"type":"ping"}'
        scraper._record_frame("send", data, is_binary=False)
        scraper._capture_file.close()

        lines = capture.read_text().strip().split("\n")
        record = json.loads(lines[0])
        assert record["direction"] == "send"
        assert record["is_binary"] is False
        assert record["data"] == '{"type":"ping"}'

    def test_record_frame_no_file(self, scraper):
        scraper._capture_file = None
        scraper._record_frame("receive", b"data", True)

    def test_record_large_text_truncated(self, scraper, tmp_path):
        capture = tmp_path / "test.jsonl"
        scraper._capture_file = open(capture, "a", encoding="utf-8")

        long_text = "x" * 5000
        scraper._record_frame("receive", long_text, is_binary=False)
        scraper._capture_file.close()

        record = json.loads(capture.read_text().strip())
        assert len(record["data"]) == 2000

    def test_record_timestamp_format(self, scraper, tmp_path):
        capture = tmp_path / "test.jsonl"
        scraper._capture_file = open(capture, "a", encoding="utf-8")

        scraper._record_frame("receive", "test", is_binary=False)
        scraper._capture_file.close()

        record = json.loads(capture.read_text().strip())
        assert record["timestamp"].endswith("Z")
        assert "T" in record["timestamp"]

    def test_multiple_frames(self, scraper, tmp_path):
        capture = tmp_path / "test.jsonl"
        scraper._capture_file = open(capture, "a", encoding="utf-8")

        for i in range(5):
            scraper._record_frame("receive", f"frame_{i}", is_binary=False)
        scraper._capture_file.close()

        lines = capture.read_text().strip().split("\n")
        assert len(lines) == 5
        for line in lines:
            record = json.loads(line)
            assert "timestamp" in record


# ---------------------------------------------------------------
# _init_capture_file / _close_capture
# ---------------------------------------------------------------

class TestCaptureFileLifecycle:
    def test_init_creates_file(self, scraper, tmp_path, monkeypatch):
        monkeypatch.setattr("scrapers.live._OUTPUT_DIR", tmp_path)
        scraper._room_id = "room123"
        scraper._init_capture_file()

        assert scraper._capture_file is not None
        assert not scraper._capture_file.closed
        assert "room123" in str(scraper._capture_path)
        assert scraper._capture_path.suffix == ".jsonl"

        scraper._close_capture()
        assert scraper._capture_file.closed

    def test_close_without_init(self, scraper):
        scraper._capture_file = None
        scraper._close_capture()

    def test_double_close(self, scraper, tmp_path, monkeypatch):
        monkeypatch.setattr("scrapers.live._OUTPUT_DIR", tmp_path)
        scraper._init_capture_file()
        scraper._close_capture()
        scraper._close_capture()


# ---------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------

class TestScraperInit:
    def test_default_state(self):
        s = LiveBarrageScraper()
        assert s.browser is None
        assert s._messages == []
        assert s._ws_connections == []
        assert s._capture_file is None
        assert s._room_id == ""
        assert s._room_url == ""
        assert s._running is False
        assert s._ws_frame_count == 0

    def test_with_browser(self):
        mock = object()
        s = LiveBarrageScraper(browser=mock)
        assert s.browser is mock


# ---------------------------------------------------------------
# Edge cases in binary parsing
# ---------------------------------------------------------------

class TestBinaryParsingEdgeCases:
    def test_gzip_with_protobuf_prefix(self, scraper):
        payload = json.dumps({"type": "chat", "content": "test"}).encode()
        compressed = gzip.compress(payload)
        data = b"\x08\x01\x12\x04" + compressed
        msgs = scraper._try_parse_frame(data)
        assert len(msgs) >= 1

    def test_nested_json_in_binary(self, scraper):
        inner = json.dumps({"type": "chat", "content": "embedded"})
        data = b"\x00\x01\x02" + inner.encode("utf-8") + b"\x00\x01"
        msgs = scraper._parse_binary_frame(data, "ts")
        assert isinstance(msgs, list)

    def test_large_binary_frame(self, scraper):
        data = os.urandom(10000)
        msgs = scraper._try_parse_frame(data)
        assert isinstance(msgs, list)
