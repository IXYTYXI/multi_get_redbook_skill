"""Xiaohongshu request signing (``x-s`` / ``x-t`` / ``x-s-common``).

INDEPENDENT IMPLEMENTATION — this does not copy third-party (e.g. MediaCrawler
fork) source; that project is a validated reference for the *approach* only.

Approach (browser-injection, login-gated)
-----------------------------------------
Xiaohongshu requires a signature header set on virtually every web API call. The
hard, obfuscated core values ``x-s`` and ``x-t`` are produced by the *page's own*
JavaScript. Inside a logged-in Playwright context we call the site's signer
(``window._webmsxyw`` on the pc-web build) via ``page.evaluate`` and read back
``X-s`` / ``X-t``. The surrounding envelope — ``x-s-common`` — is then assembled
in Python from that core value plus the device fields (``a1`` from the cookie,
``b1`` from ``localStorage``). This avoids reversing the obfuscated algorithm and
is resilient to most of its updates: whenever XHS ships a new signer, the page
still exposes it, so ``x-s`` / ``x-t`` keep working with no change here.

Validation note
---------------
The ``x-s-common`` envelope (version strings, the ``x9`` checksum) can only be
verified against a live logged-in session, which needs a real user cookie. Until
that live pass runs, treat the envelope layout as best-effort; if XHS returns a
risk-control code (300012 / 300015), the client surfaces it so the envelope can
be tuned. ``x-s`` / ``x-t`` come straight from the page and are not affected.
"""
import base64
import json
import secrets
from typing import Any, Dict, Optional, Union


# ---------------------------------------------------------------------------
# x-s-common helpers
# ---------------------------------------------------------------------------

# The pc-web client identifies itself with these constants inside x-s-common.
# They travel as plain metadata; keep them in one place so a live-validation
# tweak is a one-line change.
_PLATFORM = "xhs-pc-web"
_XHS_VERSION = "3.7.8-2"
_XHS_BUILD = "4.27.2"


def _build_crc32_table() -> list:
    """Standard reflected CRC-32 table (polynomial 0xEDB88320).

    Generated rather than hard-coded so the 256 magic constants cannot be
    mis-transcribed. XHS's ``x9`` checksum is a CRC-32 variant over this table.
    """
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (0xEDB88320 ^ (c >> 1)) if (c & 1) else (c >> 1)
        table.append(c & 0xFFFFFFFF)
    return table


_CRC32_TABLE = _build_crc32_table()


def _mrc(text: str) -> int:
    """XHS ``x9`` checksum: CRC-32 over ``text`` with the trailing XOR XHS adds.

    Mirrors the page's ``mrc`` helper: seed all-ones, table-drive per char, then
    finalise with ``(crc ^ 0xFFFFFFFF) ^ 0xEDB88320``. Returned as a signed
    32-bit int to match the JavaScript number the page emits.
    """
    crc = 0xFFFFFFFF
    for ch in text:
        crc = _CRC32_TABLE[(crc ^ ord(ch)) & 0xFF] ^ (crc >> 8)
    value = ((crc ^ 0xFFFFFFFF) ^ 0xEDB88320) & 0xFFFFFFFF
    # Interpret as signed 32-bit (JS bitwise result).
    return value - 0x100000000 if value >= 0x80000000 else value


def build_x_s_common(a1: str, b1: str, x_s: str, x_t: str) -> str:
    """Assemble the base64 ``x-s-common`` envelope from device + core values."""
    common = {
        "s0": 3,
        "s1": "",
        "x0": "1",
        "x1": _XHS_VERSION,
        "x2": "Windows",
        "x3": _PLATFORM,
        "x4": _XHS_BUILD,
        "x5": a1,
        "x6": x_t,
        "x7": x_s,
        "x8": b1,
        "x9": _mrc(x_t + x_s + b1),
        "x10": 1,
    }
    payload = json.dumps(common, separators=(",", ":"), ensure_ascii=False)
    return base64.b64encode(payload.encode("utf-8")).decode("utf-8")


def _b3_traceid() -> str:
    """16-hex-char trace id, same shape XHS puts on ``x-b3-traceid``."""
    return secrets.token_hex(8)


class SignerUnavailableError(RuntimeError):
    """Raised when the logged-in page does not expose XHS's signer function."""


async def sign_request(
    page: Any,
    uri: str,
    data: Optional[Union[Dict, str]] = None,
    method: str = "GET",
    a1: str = "",
) -> Dict[str, str]:
    """Return the signed header set for one request.

    Args:
        page: a logged-in Playwright page (Xiaohongshu open) used to compute the
            core signature value in-browser.
        uri: API path to sign. For GET requests this MUST already include the
            query string (``/api/...path?a=b``), because XHS signs the full URL.
        data: POST payload object (``None`` for GET).
        method: ``GET`` or ``POST`` (informational; signing keys off ``uri``/``data``).
        a1: the ``a1`` value from the login cookie (device fingerprint).

    Returns:
        ``{"x-s": ..., "x-t": ..., "x-s-common": ..., "x-b3-traceid": ...}``

    Raises:
        SignerUnavailableError: the page has no ``_webmsxyw`` (not logged in / not
            fully loaded / XHS renamed the signer).
    """
    core = await page.evaluate(
        """([uri, data]) => {
            const fn = window._webmsxyw || window.__webmsxyw;
            if (typeof fn !== 'function') return null;
            try {
                return fn(uri, data === undefined ? undefined : data);
            } catch (e) {
                return {error: String(e)};
            }
        }""",
        [uri, data],
    )
    if not core:
        raise SignerUnavailableError(
            "页面未暴露签名函数 window._webmsxyw。请确认：\n"
            "  1) cookies.json / XHS_COOKIE 是有效的已登录态（含 a1、web_session）；\n"
            "  2) 浏览器已导航到 xiaohongshu.com 且页面脚本加载完成。\n"
            "在无登录态下 XHS 不会注入签名器，因此无法联调。"
        )
    if "error" in core:
        raise SignerUnavailableError(f"签名函数调用失败: {core['error']}")

    x_s = core.get("X-s") or core.get("x-s") or ""
    x_t = str(core.get("X-t") or core.get("x-t") or "")

    b1 = await page.evaluate(
        "() => (window.localStorage && window.localStorage.getItem('b1')) || ''"
    )

    return {
        "x-s": x_s,
        "x-t": x_t,
        "x-s-common": build_x_s_common(a1, b1 or "", x_s, x_t),
        "x-b3-traceid": _b3_traceid(),
    }
