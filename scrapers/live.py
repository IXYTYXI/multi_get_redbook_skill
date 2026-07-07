"""Live-stream barrage (弹幕) capture via Playwright WebSocket interception.

Uses headed Chromium to navigate to a Xiaohongshu live room and intercepts
the WSS connection (URL contains ``longlink``) to capture all frames.
Binary frames are decompressed (gzip) and heuristically parsed for barrage
content; all raw frames are saved to a JSONL file for later protocol analysis.
"""
import asyncio
import base64
import gzip
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable

from models.data import LiveBarrageInfo

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


class LiveBarrageScraper:
    """Capture live-stream barrage messages from a Xiaohongshu room."""

    def __init__(self, browser=None):
        self.browser = browser
        self._messages: List[LiveBarrageInfo] = []
        self._ws_connections = []
        self._capture_file = None
        self._capture_path: Optional[Path] = None
        self._room_id = ""
        self._room_url = ""
        self._running = False
        self._on_message: Optional[Callable] = None
        self._ws_frame_count = 0
        self._last_frame_time = 0.0

    # ------------------------------------------------------------------
    # URL / room-id helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_room_id(url: str) -> str:
        m = re.search(r"/(?:hina/livestream|live)/([A-Za-z0-9_]+)", url)
        if m:
            return m.group(1)
        m = re.search(r"[?&]room_id=([A-Za-z0-9_]+)", url)
        if m:
            return m.group(1)
        parts = url.rstrip("/").split("/")
        return parts[-1] if parts else "unknown"

    # ------------------------------------------------------------------
    # Raw capture file (JSONL)
    # ------------------------------------------------------------------

    def _init_capture_file(self):
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._capture_path = _OUTPUT_DIR / f"ws_capture_{self._room_id}_{ts}.jsonl"
        self._capture_file = open(self._capture_path, "a", encoding="utf-8")
        print(f"[Live] Raw WS capture -> {self._capture_path}")

    def _record_frame(self, direction: str, payload, is_binary: bool):
        if not self._capture_file:
            return
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "direction": direction,
            "is_binary": is_binary,
            "size": len(payload) if payload else 0,
        }
        if is_binary and isinstance(payload, (bytes, bytearray)):
            record["data_b64"] = base64.b64encode(payload).decode("ascii")
            record["data_hex_head"] = payload[:128].hex()
        else:
            text = payload if isinstance(payload, str) else str(payload)
            record["data"] = text[:2000]
        try:
            self._capture_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._capture_file.flush()
        except Exception:
            pass

    def _close_capture(self):
        if self._capture_file and not self._capture_file.closed:
            self._capture_file.close()
            print(f"[Live] Capture saved: {self._capture_path}")

    # ------------------------------------------------------------------
    # Frame parsing (best-effort heuristic)
    # ------------------------------------------------------------------

    def _try_parse_frame(self, payload) -> List[LiveBarrageInfo]:
        now_ts = datetime.utcnow().isoformat() + "Z"

        if isinstance(payload, str):
            return self._parse_text_frame(payload, now_ts)
        if isinstance(payload, (bytes, bytearray)):
            return self._parse_binary_frame(payload, now_ts)
        return []

    def _parse_text_frame(self, text: str, ts: str) -> List[LiveBarrageInfo]:
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
        msg = self._json_to_barrage(obj, ts, text)
        return [msg] if msg else []

    def _parse_binary_frame(self, data: bytes, ts: str) -> List[LiveBarrageInfo]:
        raw_b64 = base64.b64encode(data).decode("ascii")

        decompressed = self._try_gzip(data)
        source = decompressed if decompressed is not None else data

        # Try JSON on the decompressed payload
        try:
            obj = json.loads(source)
            msg = self._json_to_barrage(obj, ts, raw_b64)
            if msg:
                return [msg]
        except Exception:
            pass

        return self._extract_barrage_strings(source, ts, raw_b64)

    @staticmethod
    def _try_gzip(data: bytes) -> Optional[bytes]:
        """Try gzip decompression from the start or at the first gzip header."""
        try:
            return gzip.decompress(data)
        except Exception:
            pass
        # Scan for gzip magic bytes (0x1f 0x8b)
        idx = data.find(b"\x1f\x8b")
        if idx > 0:
            try:
                return gzip.decompress(data[idx:])
            except Exception:
                pass
        return None

    def _json_to_barrage(self, obj: dict, ts: str, raw: str) -> Optional[LiveBarrageInfo]:
        if not isinstance(obj, dict):
            return None

        msg_type = "unknown"
        for key in ("type", "msg_type", "msgType", "action", "cmd"):
            val = obj.get(key)
            if val is None:
                continue
            t = str(val).lower()
            if any(k in t for k in ("barrage", "chat", "comment", "danmu", "msg")):
                msg_type = "barrage"
            elif "gift" in t:
                msg_type = "gift"
            elif any(k in t for k in ("enter", "join", "member")):
                msg_type = "enter"
            elif "follow" in t:
                msg_type = "follow"
            elif "like" in t:
                msg_type = "like"
            if msg_type != "unknown":
                break

        content = ""
        for key in ("content", "text", "msg", "message", "body", "data"):
            v = obj.get(key)
            if v and isinstance(v, str):
                content = v
                break

        user_name, user_id = "", ""
        for ukey in ("user", "sender", "from", "userInfo"):
            u = obj.get(ukey)
            if isinstance(u, dict):
                user_name = str(u.get("nickname", u.get("name", u.get("nickName", ""))))
                user_id = str(u.get("id", u.get("userId", u.get("user_id", ""))))
                break
        if not user_name:
            user_name = str(obj.get("nickname", obj.get("userName", "")))
        if not user_id:
            user_id = str(obj.get("userId", obj.get("user_id", "")))

        if not content and not user_name and msg_type == "unknown":
            return None

        return LiveBarrageInfo(
            user_id=user_id,
            user_name=user_name,
            content=content[:500],
            message_type=msg_type,
            timestamp=ts,
            room_id=self._room_id,
            room_url=self._room_url,
            raw_data=raw[:1000],
        )

    def _extract_barrage_strings(
        self, data: bytes, ts: str, raw_b64: str
    ) -> List[LiveBarrageInfo]:
        """Extract readable CJK/ASCII strings from binary data as best-effort barrage."""
        results: List[LiveBarrageInfo] = []
        strings = self._find_utf8_strings(data, min_len=2)
        cjk = [s for s in strings if any("一" <= c <= "鿿" for c in s)]
        if not cjk:
            return results

        for i in range(0, len(cjk) - 1, 2):
            user_candidate = cjk[i]
            content_candidate = cjk[i + 1]
            if len(user_candidate) > 30 and len(content_candidate) <= 30:
                user_candidate, content_candidate = content_candidate, user_candidate
            results.append(
                LiveBarrageInfo(
                    user_name=user_candidate[:50],
                    content=content_candidate[:200],
                    message_type="barrage",
                    timestamp=ts,
                    room_id=self._room_id,
                    room_url=self._room_url,
                    raw_data=raw_b64[:500],
                )
            )

        if len(cjk) % 2 == 1:
            results.append(
                LiveBarrageInfo(
                    content=cjk[-1][:200],
                    message_type="unknown",
                    timestamp=ts,
                    room_id=self._room_id,
                    room_url=self._room_url,
                    raw_data=raw_b64[:500],
                )
            )
        return results

    @staticmethod
    def _find_utf8_strings(data: bytes, min_len: int = 2) -> List[str]:
        """Greedily extract UTF-8 segments containing CJK or printable ASCII."""
        found: List[str] = []
        buf = bytearray()
        for b in data:
            buf.append(b)
            if len(buf) > 300:
                try:
                    s = buf.decode("utf-8")
                    if len(s) >= min_len:
                        found.append(s)
                except UnicodeDecodeError:
                    pass
                buf.clear()
                continue
            if b < 0x20 and b not in (0x09, 0x0A, 0x0D):
                if buf[:-1]:
                    try:
                        s = bytes(buf[:-1]).decode("utf-8")
                        if len(s) >= min_len and s.isprintable():
                            found.append(s)
                    except UnicodeDecodeError:
                        pass
                buf.clear()
        if buf:
            try:
                s = bytes(buf).decode("utf-8")
                if len(s) >= min_len and s.isprintable():
                    found.append(s)
            except UnicodeDecodeError:
                pass
        return found

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self, room_url: str) -> str:
        """Navigate to the live room and return the room_id."""
        if not self.browser:
            raise RuntimeError("LiveBarrageScraper requires a browser instance")

        self._room_url = room_url
        self._room_id = self._extract_room_id(room_url)

        page = self.browser.page
        print(f"[Live] Navigating to: {room_url}")
        print(f"[Live] Room ID: {self._room_id}")

        try:
            await page.goto(room_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[Live] Navigation warning: {e}")
        await asyncio.sleep(3)
        return self._room_id

    async def listen(
        self,
        room_url: str,
        duration: Optional[int] = None,
        on_message: Optional[Callable[[LiveBarrageInfo], None]] = None,
    ) -> List[LiveBarrageInfo]:
        """Listen for barrage messages via Playwright WebSocket interception.

        Opens the live room in headed Chromium, intercepts the ``longlink``
        WebSocket, captures every frame to a JSONL file, and returns parsed
        ``LiveBarrageInfo`` objects.
        """
        if not self.browser:
            raise RuntimeError("LiveBarrageScraper requires a browser instance")

        self._on_message = on_message
        self._messages = []
        self._ws_connections = []
        self._ws_frame_count = 0
        self._running = True
        self._room_url = room_url
        self._room_id = self._extract_room_id(room_url)

        self._init_capture_file()

        page = self.browser.page

        # ---- WebSocket interception ----

        def _on_ws(ws):
            url = ws.url
            is_target = "longlink" in url
            label = "TARGET" if is_target else "other"
            print(f"[Live] WS opened [{label}]: {url[:100]}")
            if not is_target:
                return

            self._ws_connections.append(ws)
            self._last_frame_time = time.time()
            print(f"[Live] Target WebSocket connected — intercepting frames")

            def _on_recv(frame_data):
                if not self._running:
                    return
                payload = frame_data.get("payload", frame_data) if isinstance(frame_data, dict) else frame_data
                self._ws_frame_count += 1
                self._last_frame_time = time.time()
                is_bin = isinstance(payload, (bytes, bytearray))
                self._record_frame("receive", payload, is_bin)
                try:
                    for msg in self._try_parse_frame(payload):
                        self._messages.append(msg)
                        if self._on_message:
                            self._on_message(msg)
                except Exception as exc:
                    if self._ws_frame_count <= 5:
                        print(f"[Live] Parse error (frame #{self._ws_frame_count}): {exc}")

            def _on_sent(frame_data):
                if not self._running:
                    return
                payload = frame_data.get("payload", frame_data) if isinstance(frame_data, dict) else frame_data
                is_bin = isinstance(payload, (bytes, bytearray))
                self._record_frame("send", payload, is_bin)

            def _on_close():
                print(f"[Live] WS closed (total frames received: {self._ws_frame_count})")
                if ws in self._ws_connections:
                    self._ws_connections.remove(ws)

            ws.on("framereceived", _on_recv)
            ws.on("framesent", _on_sent)
            ws.on("close", _on_close)

        page.on("websocket", _on_ws)

        # ---- Navigate to the live room ----

        print(f"[Live] Opening live room: {room_url}")
        try:
            await page.goto(room_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[Live] Navigation warning: {e}")
        await asyncio.sleep(3)
        print("[Live] Page loaded — waiting for WebSocket connections...")

        wait_start = time.time()
        while not self._ws_connections and time.time() - wait_start < 30:
            await asyncio.sleep(1)

        if self._ws_connections:
            print(f"[Live] {len(self._ws_connections)} target WS connection(s) active")
        else:
            print("[Live] No target WS (longlink) after 30s — will keep monitoring")

        # ---- Main listen loop ----

        start_time = time.time()
        last_status = start_time
        reconnect_count = 0
        max_reconnect = 3
        status_interval = 30

        try:
            while self._running:
                await asyncio.sleep(1)
                now = time.time()
                elapsed = now - start_time

                if duration and elapsed >= duration:
                    print(f"[Live] Duration limit ({duration}s) reached")
                    break

                if now - last_status >= status_interval:
                    print(
                        f"[Live] {len(self._messages)} msgs | "
                        f"{self._ws_frame_count} frames | "
                        f"{int(elapsed)}s | "
                        f"WS: {len(self._ws_connections)}"
                    )
                    last_status = now

                # Auto-reconnect if the target WS dropped
                if (
                    not self._ws_connections
                    and self._ws_frame_count > 0
                    and reconnect_count < max_reconnect
                    and now - self._last_frame_time > 15
                ):
                    reconnect_count += 1
                    print(
                        f"[Live] WS lost — reconnect {reconnect_count}/{max_reconnect}..."
                    )
                    try:
                        await page.reload(
                            wait_until="domcontentloaded", timeout=60000
                        )
                        await asyncio.sleep(5)
                        self._last_frame_time = time.time()
                    except Exception as e:
                        print(f"[Live] Reconnect failed: {e}")

        except KeyboardInterrupt:
            print("\n[Live] Interrupted (Ctrl+C)")
        except Exception as e:
            print(f"[Live] Error in listen loop: {e}")
        finally:
            self._running = False
            self._close_capture()
            print(
                f"[Live] Done: {len(self._messages)} parsed messages, "
                f"{self._ws_frame_count} raw frames captured"
            )

        return self._messages

    async def disconnect(self) -> None:
        """Stop listening and release resources."""
        self._running = False
        self._close_capture()
