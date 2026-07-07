"""Live-stream barrage capture via Playwright WebSocket interception.

Uses headed Chromium to navigate to a Xiaohongshu live room, intercepts the
WebSocket connection (URL containing 'longlink'), and captures all frames.
Binary frames are attempted protobuf+gzip decode; failures fall back to hex dump.
All raw frames are persisted to a JSONL file for offline protocol analysis.
"""

import asyncio
import base64
import gzip
import json
import os
import re
import time
import zlib
from datetime import datetime, timezone
from typing import List, Optional, Callable

from models.data import LiveBarrageInfo
from config.settings import LIVE_WS_OUTPUT_DIR


class RawFrameRecorder:
    """Append-only JSONL writer for raw WebSocket frames."""

    def __init__(self, room_id: str, output_dir: str = None):
        output_dir = output_dir or LIVE_WS_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = os.path.join(output_dir, f"ws_capture_{room_id}_{ts}.jsonl")
        self._file = open(self._path, "a", encoding="utf-8")

    def record(self, direction: str, data, is_binary: bool = False):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "is_binary": is_binary,
        }
        if is_binary and isinstance(data, (bytes, bytearray)):
            entry["data_base64"] = base64.b64encode(data).decode()
            entry["data_hex"] = data[:256].hex()
            entry["size"] = len(data)
        else:
            entry["data"] = str(data) if data else ""
        self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._file.flush()

    @property
    def path(self):
        return self._path

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()


def _extract_room_id(url: str) -> str:
    m = re.search(r"/live(?:stream)?/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else "unknown"


def _read_varint(data: bytes, pos: int):
    """Read a protobuf varint starting at pos. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        shift += 7
        pos += 1
        if not (b & 0x80):
            return result, pos
    return result, pos


def _extract_protobuf_strings(data: bytes) -> list:
    """Best-effort extraction of UTF-8 strings from protobuf wire format."""
    strings = []
    i = 0
    while i < len(data) - 1:
        tag_start = i
        try:
            tag, i = _read_varint(data, i)
        except Exception:
            i = tag_start + 1
            continue

        wire_type = tag & 0x07

        if wire_type == 2:
            try:
                length, i = _read_varint(data, i)
            except Exception:
                i = tag_start + 1
                continue
            if 0 < length <= 10000 and i + length <= len(data):
                chunk = data[i : i + length]
                try:
                    text = chunk.decode("utf-8")
                    if len(text) >= 2 and all(
                        c.isprintable() or c in "\n\r\t" for c in text
                    ):
                        strings.append(text)
                except (UnicodeDecodeError, ValueError):
                    pass
                i += length
            else:
                i = tag_start + 1
        elif wire_type == 0:
            try:
                _, i = _read_varint(data, i)
            except Exception:
                i = tag_start + 1
        elif wire_type == 1:
            i += 8
        elif wire_type == 5:
            i += 4
        else:
            i = tag_start + 1
    return strings


def _try_decompress(data: bytes) -> Optional[bytes]:
    """Try gzip then raw deflate on the payload or sub-slices."""
    for skip in (0, 2, 4, 8, 13, 16):
        payload = data[skip:] if skip else data
        if len(payload) < 2:
            continue
        if payload[:2] == b"\x1f\x8b":
            try:
                return gzip.decompress(payload)
            except Exception:
                pass
        try:
            return zlib.decompress(payload)
        except Exception:
            pass
        try:
            return zlib.decompress(payload, -zlib.MAX_WBITS)
        except Exception:
            pass
    return None


def _brute_scan_strings(data: bytes, min_len: int = 3) -> list:
    """Scan raw bytes for contiguous printable UTF-8 segments."""
    strings = []
    buf = bytearray()
    i = 0
    while i < len(data):
        for width in (1, 2, 3, 4):
            if i + width > len(data):
                break
            try:
                ch = data[i : i + width].decode("utf-8")
                if len(ch) == 1 and (ch.isprintable() or ch in "\n\r\t"):
                    buf.extend(data[i : i + width])
                    i += width
                    break
            except UnicodeDecodeError:
                continue
        else:
            if len(buf) >= min_len:
                try:
                    strings.append(buf.decode("utf-8", errors="ignore").strip())
                except Exception:
                    pass
            buf.clear()
            i += 1
    if len(buf) >= min_len:
        try:
            strings.append(buf.decode("utf-8", errors="ignore").strip())
        except Exception:
            pass
    return [s for s in strings if len(s) >= min_len]


def _parse_binary_frame(data: bytes) -> dict:
    """Attempt to decode a binary WebSocket frame."""
    result = {"raw_size": len(data), "strings": [], "decompressed": False}

    decompressed = _try_decompress(data)
    if decompressed:
        result["decompressed"] = True

    target = decompressed if decompressed else data
    strings = _extract_protobuf_strings(target)
    if not strings:
        strings = _brute_scan_strings(target)
    result["strings"] = strings
    return result


class LiveBarrageScraper:
    """Capture live-stream barrage messages from a Xiaohongshu room."""

    def __init__(self, browser=None):
        self.browser = browser
        self._messages: List[LiveBarrageInfo] = []
        self._recorder: Optional[RawFrameRecorder] = None
        self._ws_connected = False
        self._stop_event: Optional[asyncio.Event] = None
        self._room_id = ""
        self._room_url = ""
        self._last_frame_time = 0.0
        self._frame_count = 0
        self._on_message: Optional[Callable] = None

    async def connect(self, room_url: str) -> str:
        self._room_url = room_url
        self._room_id = _extract_room_id(room_url)
        self._recorder = RawFrameRecorder(self._room_id)
        self._stop_event = asyncio.Event()
        print(f"[Live] Room ID: {self._room_id}")
        print(f"[Live] Raw frames -> {self._recorder.path}")
        return self._room_id

    def _on_ws_open(self, ws):
        url = ws.url
        is_target = "longlink" in url.lower()
        print(
            f"[Live] WebSocket opened: {url[:120]}..."
            + (" *** TARGET ***" if is_target else "")
        )

        def on_recv(payload):
            is_binary = isinstance(payload, (bytes, bytearray))
            if self._recorder:
                self._recorder.record("receive", payload, is_binary)
            if is_target:
                self._last_frame_time = time.time()
                self._frame_count += 1
                self._process_frame(payload, is_binary)

        def on_sent(payload):
            is_binary = isinstance(payload, (bytes, bytearray))
            if self._recorder:
                self._recorder.record("send", payload, is_binary)
            if is_target:
                self._last_frame_time = time.time()

        def on_close():
            if is_target:
                self._ws_connected = False
                print(f"[Live] Target WebSocket disconnected")

        ws.on("framereceived", on_recv)
        ws.on("framesent", on_sent)
        ws.on("close", on_close)

        if is_target:
            self._ws_connected = True
            self._last_frame_time = time.time()

    def _process_frame(self, payload, is_binary: bool):
        if not is_binary:
            text = payload if isinstance(payload, str) else payload.decode("utf-8", errors="replace")
            try:
                data = json.loads(text)
                msg = self._parse_json_message(data)
                if msg:
                    self._emit(msg)
                return
            except (json.JSONDecodeError, ValueError):
                pass
            msg = LiveBarrageInfo(
                content=text[:500],
                message_type="text",
                timestamp=datetime.now(timezone.utc).isoformat(),
                room_id=self._room_id,
                room_url=self._room_url,
                raw_data=text[:500],
            )
            self._emit(msg)
            return

        raw = payload if isinstance(payload, (bytes, bytearray)) else payload.encode()
        parsed = _parse_binary_frame(raw)
        strings = parsed.get("strings", [])

        if strings:
            msg = self._infer_from_strings(strings, raw)
            if msg:
                self._emit(msg)
                return

        if self._frame_count <= 20 or self._frame_count % 100 == 0:
            print(
                f"[Live] Binary frame #{self._frame_count}: {len(raw)}B "
                f"{'(decompressed) ' if parsed['decompressed'] else ''}"
                f"hex={raw[:32].hex()}..."
            )

    def _parse_json_message(self, data: dict) -> Optional[LiveBarrageInfo]:
        content = str(
            data.get("content") or data.get("text") or data.get("msg") or ""
        )
        user = data.get("user") or data.get("sender") or {}
        user_name = ""
        user_id = ""
        if isinstance(user, dict):
            user_name = str(
                user.get("name") or user.get("nickname") or user.get("nick_name") or ""
            )
            user_id = str(user.get("id") or user.get("user_id") or "")

        msg_type = "unknown"
        t = str(data.get("type") or data.get("method") or "").lower()
        if any(k in t for k in ("chat", "barrage", "comment", "danmu")):
            msg_type = "barrage"
        elif "gift" in t:
            msg_type = "gift"
        elif any(k in t for k in ("enter", "join", "member")):
            msg_type = "enter"
        elif "follow" in t:
            msg_type = "follow"
        elif "like" in t:
            msg_type = "like"

        if content or user_name:
            return LiveBarrageInfo(
                user_id=user_id,
                user_name=user_name,
                content=content,
                message_type=msg_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                room_id=self._room_id,
                room_url=self._room_url,
                raw_data=json.dumps(data, ensure_ascii=False)[:500],
            )
        return None

    def _infer_from_strings(self, strings: list, raw: bytes) -> Optional[LiveBarrageInfo]:
        meaningful = [s for s in strings if len(s) >= 2 and not s.startswith("http")]
        if not meaningful:
            return None
        content = max(meaningful, key=len)
        user_name = ""
        candidates = [s for s in meaningful if s != content and len(s) < 30]
        if candidates:
            user_name = candidates[0]

        return LiveBarrageInfo(
            user_name=user_name,
            content=content,
            message_type="barrage",
            timestamp=datetime.now(timezone.utc).isoformat(),
            room_id=self._room_id,
            room_url=self._room_url,
            raw_data=base64.b64encode(raw[:200]).decode(),
        )

    def _emit(self, msg: LiveBarrageInfo):
        self._messages.append(msg)
        if self._on_message:
            try:
                self._on_message(msg)
            except Exception as e:
                print(f"[Live] Callback error: {e}")

    async def listen(
        self,
        room_url: str,
        duration: Optional[int] = None,
        on_message: Optional[Callable[[LiveBarrageInfo], None]] = None,
    ) -> List[LiveBarrageInfo]:
        self._on_message = on_message
        await self.connect(room_url)

        page = self.browser.page
        page.on("websocket", self._on_ws_open)

        print(f"[Live] Navigating to {room_url} ...")
        try:
            await page.goto(room_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[Live] Navigation warning: {e}")
        await asyncio.sleep(3)
        print("[Live] Page loaded. Waiting for WebSocket connections...")

        ws_wait = 0
        while not self._ws_connected and ws_wait < 30:
            await asyncio.sleep(1)
            ws_wait += 1

        if self._ws_connected:
            print("[Live] Target WebSocket connected! Capturing frames...")
        else:
            print(
                "[Live] No target WebSocket after 30s. "
                "Continuing to monitor (WS may appear later)."
            )

        start_time = time.time()
        last_status = start_time
        reconnect_cooldown = 0.0

        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(1)
                now = time.time()
                elapsed = now - start_time

                if duration and elapsed >= duration:
                    print(f"\n[Live] Duration limit reached ({duration}s). Stopping.")
                    break

                if now - last_status >= 30:
                    last_status = now
                    print(
                        f"[Live] {int(elapsed)}s elapsed | "
                        f"{self._frame_count} frames | "
                        f"{len(self._messages)} msgs | "
                        f"WS={'up' if self._ws_connected else 'down'}"
                    )

                # Reconnect if no frames for 60s after a previous connection
                if (
                    not self._ws_connected
                    and self._last_frame_time > 0
                    and now - self._last_frame_time > 60
                    and now - reconnect_cooldown > 30
                ):
                    print("[Live] Attempting reconnect (page reload)...")
                    reconnect_cooldown = now
                    try:
                        await page.reload(
                            wait_until="domcontentloaded", timeout=30000
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(3)

        except asyncio.CancelledError:
            print("\n[Live] Cancelled.")

        await self.disconnect()
        return list(self._messages)

    async def disconnect(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._recorder:
            print(f"[Live] Frames captured: {self._frame_count}")
            print(f"[Live] Messages parsed: {len(self._messages)}")
            print(f"[Live] Raw data saved to: {self._recorder.path}")
            self._recorder.close()
            self._recorder = None
