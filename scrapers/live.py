"""Live-stream barrage (弹幕) capture via Playwright WebSocket interception.

Opens a Xiaohongshu live-room page in a headed Chromium instance, intercepts
all WebSocket traffic, and decodes barrage / gift / enter / like events into
``LiveBarrageInfo`` objects.  Raw WebSocket frames are logged to a JSONL file
for offline protocol analysis (Phase 2).
"""
import asyncio
import base64
import gzip
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Callable

from models.data import LiveBarrageInfo

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
_CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(_CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _now_ts() -> str:
    return datetime.now(_CST).strftime("%Y%m%d_%H%M%S")


def _extract_room_id(url: str) -> str:
    m = re.search(r"/live/(\w+)", url)
    return m.group(1) if m else ""


def _try_decode_frame(raw: bytes) -> Optional[dict]:
    """Best-effort decode of a binary WebSocket frame.

    Xiaohongshu live frames are protobuf-wrapped, gzip-compressed payloads.
    Without a compiled .proto schema we fall back to:
      1. Try gzip decompression.
      2. Try UTF-8 decode on the (decompressed) payload.
      3. Try JSON parse.
    Returns a dict on success, None otherwise.
    """
    payload = raw
    try:
        payload = gzip.decompress(raw)
    except Exception:
        pass
    try:
        text = payload.decode("utf-8", errors="replace")
        return json.loads(text)
    except Exception:
        pass
    # Attempt scanning for JSON substrings embedded in protobuf wrappers.
    try:
        text = payload.decode("utf-8", errors="replace")
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
    except Exception:
        pass
    return None


def _guess_message_type(data: dict) -> str:
    """Heuristic classification of a decoded message dict."""
    raw = json.dumps(data, ensure_ascii=False).lower()
    if any(k in raw for k in ("chat", "comment", "danmu", "弹幕", "barrage")):
        return "barrage"
    if any(k in raw for k in ("gift", "礼物", "reward")):
        return "gift"
    if any(k in raw for k in ("enter", "join", "member", "进入")):
        return "enter"
    if any(k in raw for k in ("like", "点赞", "digg")):
        return "like"
    if any(k in raw for k in ("follow", "关注")):
        return "follow"
    return "unknown"


def _extract_user(data: dict) -> tuple:
    """Try to extract (user_id, user_name) from a decoded dict."""
    for key in ("user", "User", "sender", "Sender"):
        u = data.get(key)
        if isinstance(u, dict):
            uid = str(u.get("id", u.get("user_id", u.get("userId", ""))))
            name = u.get("nickname", u.get("nick_name", u.get("nickName", u.get("name", ""))))
            return uid, str(name)
    uid = str(data.get("user_id", data.get("userId", "")))
    name = data.get("nickname", data.get("user_name", data.get("userName", "")))
    return uid, str(name)


def _extract_content(data: dict) -> str:
    for key in ("content", "Content", "text", "msg", "message", "body"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


class LiveBarrageScraper:
    """Capture live-stream barrage messages from a Xiaohongshu room."""

    def __init__(self, browser=None, capture_dir: Optional[str] = None):
        self.browser = browser
        self._capture_dir = Path(capture_dir) if capture_dir else _OUTPUT_DIR
        self._messages: List[LiveBarrageInfo] = []
        self._ws_connections: list = []
        self._capture_file = None
        self._stop_event: Optional[asyncio.Event] = None
        self._room_id = ""
        self._room_url = ""
        self._frame_count = 0
        self._ws_matched = False

    async def listen(
        self,
        room_url: str,
        duration: Optional[int] = None,
        on_message: Optional[Callable[[LiveBarrageInfo], None]] = None,
    ) -> List[LiveBarrageInfo]:
        from core.browser import XhsBrowser

        self._room_url = room_url
        self._room_id = _extract_room_id(room_url) or "unknown"
        self._messages = []
        self._stop_event = asyncio.Event()

        self._capture_dir.mkdir(parents=True, exist_ok=True)
        cap_path = self._capture_dir / f"ws_capture_{self._room_id}_{_now_ts()}.jsonl"
        self._capture_file = open(cap_path, "a", encoding="utf-8")
        print(f"[Live] Raw WebSocket frames → {cap_path}")

        own_browser = self.browser is None
        browser = self.browser or XhsBrowser()

        try:
            if own_browser:
                await browser.start(headless=False)
                if not await browser.ensure_login():
                    raise RuntimeError("Login required. Run 'python main.py login' first.")

            page = browser.page

            page.on("websocket", lambda ws: self._on_websocket(ws, on_message))

            print(f"[Live] Navigating to {room_url} ...")
            await page.goto(room_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # Also listen on any new pages/popups.
            browser.context.on("page", lambda p: p.on("websocket", lambda ws: self._on_websocket(ws, on_message)))

            print(f"[Live] Listening for barrage messages (room: {self._room_id}) ...")
            if duration:
                print(f"[Live] Will stop after {duration}s.")

            await self._wait_loop(duration)

        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            print("\n[Live] Interrupted by user.")
        finally:
            if self._capture_file:
                self._capture_file.close()
                self._capture_file = None
            if own_browser:
                await browser.close()

        print(f"[Live] Session ended. Captured {len(self._messages)} messages, {self._frame_count} raw frames.")
        return self._messages

    async def _wait_loop(self, duration: Optional[int]):
        start = time.monotonic()
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(1)
                if duration and (time.monotonic() - start) >= duration:
                    print(f"[Live] Duration limit ({duration}s) reached.")
                    break
                elapsed = int(time.monotonic() - start)
                if elapsed > 0 and elapsed % 30 == 0:
                    ws_status = "connected" if self._ws_matched else "waiting"
                    print(
                        f"[Live] {elapsed}s elapsed | {len(self._messages)} msgs | "
                        f"{self._frame_count} frames | WS: {ws_status}"
                    )
        except asyncio.CancelledError:
            pass

    def _on_websocket(self, ws, on_message: Optional[Callable]):
        url = ws.url
        is_target = "longlink" in url or "ws" in url.split("?")[0].lower()

        tag = "TARGET" if is_target else "other"
        print(f"[Live] WebSocket opened [{tag}]: {url[:120]}...")
        self._log_frame("ws_open", "info", url)

        if is_target:
            self._ws_matched = True

        def handle_send(data):
            self._on_frame("send", data, on_message, is_target)

        def handle_recv(data):
            self._on_frame("receive", data, on_message, is_target)

        def handle_close():
            print(f"[Live] WebSocket closed [{tag}]: {url[:80]}...")
            self._log_frame("ws_close", "info", url)

        ws.on("framesent", handle_send)
        ws.on("framereceived", handle_recv)
        ws.on("close", handle_close)
        self._ws_connections.append(ws)

    def _on_frame(self, direction: str, data, on_message: Optional[Callable], is_target: bool):
        self._frame_count += 1
        ts = _now_iso()

        if isinstance(data, bytes):
            encoded = base64.b64encode(data).encode("ascii").decode("ascii")
            self._log_frame(direction, "binary", encoded, len(data))

            if not is_target:
                return

            decoded = _try_decode_frame(data)
            if decoded:
                msg = self._dict_to_barrage(decoded, ts)
                self._emit(msg, on_message)
            else:
                self._try_extract_strings(data, ts, on_message)
        else:
            text = str(data)
            self._log_frame(direction, "text", text[:2000])

            if not is_target:
                return

            try:
                parsed = json.loads(text)
                msg = self._dict_to_barrage(parsed, ts)
                self._emit(msg, on_message)
            except json.JSONDecodeError:
                if len(text) > 4:
                    msg = LiveBarrageInfo(
                        content=text[:500],
                        message_type="unknown",
                        timestamp=ts,
                        room_id=self._room_id,
                        room_url=self._room_url,
                        raw_data=text[:2000],
                    )
                    self._emit(msg, on_message)

    def _try_extract_strings(self, data: bytes, ts: str, on_message: Optional[Callable]):
        """Scan binary data for readable string fragments that look like messages."""
        payloads = [data]
        try:
            payloads.append(gzip.decompress(data))
        except Exception:
            pass

        for payload in payloads:
            text = payload.decode("utf-8", errors="replace")
            readable = re.findall(r"[一-鿿\w@#]{2,}", text)
            if readable and len(readable) >= 2:
                content = " ".join(readable[:10])
                msg = LiveBarrageInfo(
                    content=content,
                    message_type="raw_extract",
                    timestamp=ts,
                    room_id=self._room_id,
                    room_url=self._room_url,
                    raw_data=base64.b64encode(payload[:500]).decode("ascii"),
                )
                self._emit(msg, on_message)

    def _dict_to_barrage(self, data: dict, ts: str) -> LiveBarrageInfo:
        uid, uname = _extract_user(data)
        content = _extract_content(data)
        mtype = _guess_message_type(data)
        return LiveBarrageInfo(
            user_id=uid,
            user_name=uname,
            content=content,
            message_type=mtype,
            timestamp=ts,
            room_id=self._room_id,
            room_url=self._room_url,
            raw_data=json.dumps(data, ensure_ascii=False)[:2000],
        )

    def _emit(self, msg: LiveBarrageInfo, on_message: Optional[Callable]):
        self._messages.append(msg)
        if on_message:
            try:
                on_message(msg)
            except Exception:
                pass

    def _log_frame(self, direction: str, frame_type: str, data: str, size: int = 0):
        if not self._capture_file:
            return
        record = {
            "ts": _now_iso(),
            "direction": direction,
            "type": frame_type,
            "size": size or len(data),
            "data": data,
        }
        try:
            self._capture_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._capture_file.flush()
        except Exception:
            pass

    async def connect(self, room_url: str) -> str:
        self._room_url = room_url
        self._room_id = _extract_room_id(room_url) or "unknown"
        return self._room_id

    async def disconnect(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._capture_file:
            self._capture_file.close()
            self._capture_file = None
