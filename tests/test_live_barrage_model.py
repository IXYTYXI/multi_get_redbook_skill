"""Tests for LiveBarrageInfo data model."""
import pytest
from models.data import LiveBarrageInfo


class TestLiveBarrageInfoInit:
    def test_default_values(self):
        msg = LiveBarrageInfo()
        assert msg.user_id == ""
        assert msg.user_name == ""
        assert msg.content == ""
        assert msg.message_type == ""
        assert msg.timestamp == ""
        assert msg.room_id == ""
        assert msg.room_url == ""
        assert msg.raw_data == ""

    def test_all_fields(self):
        msg = LiveBarrageInfo(
            user_id="u123",
            user_name="Alice",
            content="hello world",
            message_type="barrage",
            timestamp="2026-07-07T12:00:00Z",
            room_id="room1",
            room_url="https://www.xiaohongshu.com/live/room1",
            raw_data='{"type":"chat"}',
        )
        assert msg.user_id == "u123"
        assert msg.user_name == "Alice"
        assert msg.content == "hello world"
        assert msg.message_type == "barrage"
        assert msg.room_id == "room1"

    def test_partial_fields(self):
        msg = LiveBarrageInfo(content="test", message_type="gift")
        assert msg.content == "test"
        assert msg.message_type == "gift"
        assert msg.user_id == ""
        assert msg.user_name == ""


class TestLiveBarrageInfoToDict:
    def test_to_dict_returns_all_keys(self):
        msg = LiveBarrageInfo(user_id="u1", content="hi")
        d = msg.to_dict()
        expected_keys = {
            "user_id", "user_name", "content", "message_type",
            "timestamp", "room_id", "room_url", "raw_data",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        msg = LiveBarrageInfo(
            user_id="u1", user_name="Bob", content="hello",
            message_type="barrage", room_id="r1",
        )
        d = msg.to_dict()
        assert d["user_id"] == "u1"
        assert d["user_name"] == "Bob"
        assert d["content"] == "hello"
        assert d["message_type"] == "barrage"
        assert d["room_id"] == "r1"

    def test_to_dict_is_plain_dict(self):
        msg = LiveBarrageInfo()
        d = msg.to_dict()
        assert isinstance(d, dict)
        assert type(d) is dict


class TestLiveBarrageInfoEdgeCases:
    def test_unicode_content(self):
        msg = LiveBarrageInfo(content="你好世界🎉", user_name="测试用户")
        assert msg.content == "你好世界🎉"
        assert msg.user_name == "测试用户"
        d = msg.to_dict()
        assert d["content"] == "你好世界🎉"

    def test_long_content(self):
        long_text = "x" * 10000
        msg = LiveBarrageInfo(content=long_text)
        assert len(msg.content) == 10000

    def test_special_characters(self):
        msg = LiveBarrageInfo(content='<script>alert("xss")</script>')
        assert "<script>" in msg.content

    def test_message_types(self):
        for mtype in ("barrage", "gift", "enter", "follow", "like", "unknown"):
            msg = LiveBarrageInfo(message_type=mtype)
            assert msg.message_type == mtype
