"""Signed Xiaohongshu web-API client.

Wraps :class:`core.browser.XhsBrowser` with request signing (:mod:`core.sign`)
and in-page ``fetch`` so every call inherits the logged-in page's runtime state.
All XHS ``/api/sns/web/...`` endpoints require signing — there is no cookie-only
fast path — so scrapers go through this client rather than hitting httpx directly.
"""
import asyncio
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from config.settings import XHS_API_BASE, REQUEST_DELAY
from core.sign import sign_request


# XHS risk-control codes worth calling out explicitly.
_RISK_CODES = {
    -100: "登录态失效（未登录/Cookie 过期），请重新 `python main.py login`",
    300012: "签名/风控校验失败（x-s-common 可能需按当前版本联调修正）",
    300015: "签名/风控校验失败（x-s-common 可能需按当前版本联调修正）",
    300017: "缺少或错误的 xsec_token —— 详情/评论请求必须透传 search/list 返回的 token",
}


class XhsResponseError(RuntimeError):
    def __init__(self, code: int, msg: str, uri: str):
        self.code = code
        self.msg = msg
        hint = _RISK_CODES.get(code, "")
        super().__init__(
            f"XHS API {uri} 返回 code={code} msg={msg!r}" + (f" —— {hint}" if hint else "")
        )


class XhsClient:
    """Signed GET/POST against the edith web API through the logged-in page."""

    def __init__(self, browser, delay: float = None):
        self.browser = browser
        self._delay = REQUEST_DELAY if delay is None else delay

    async def _a1(self) -> str:
        return (await self.browser.cookie_dict()).get("a1", "")

    async def get(self, uri: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Signed GET. ``uri`` is the API path; ``params`` become the query."""
        await asyncio.sleep(self._delay)
        query = urlencode(params or {})
        sign_uri = f"{uri}?{query}" if query else uri
        headers = await sign_request(self.browser.page, sign_uri, None, "GET", await self._a1())
        url = f"{XHS_API_BASE}{sign_uri}"
        data = await self.browser.fetch_api(url, headers=headers, method="GET")
        return self._unwrap(data, uri)

    async def post(self, uri: str, payload: Optional[Dict] = None) -> Dict[str, Any]:
        """Signed POST with a JSON body."""
        await asyncio.sleep(self._delay)
        payload = payload or {}
        headers = await sign_request(self.browser.page, uri, payload, "POST", await self._a1())
        url = f"{XHS_API_BASE}{uri}"
        data = await self.browser.fetch_api(url, headers=headers, method="POST", body=payload)
        return self._unwrap(data, uri)

    @staticmethod
    def _unwrap(data: Dict[str, Any], uri: str) -> Dict[str, Any]:
        """Return ``data['data']`` on success; raise on a risk-control code."""
        if not isinstance(data, dict) or not data:
            raise XhsResponseError(-1, "empty/invalid response", uri)
        if data.get("success") is True or data.get("code") == 0:
            return data.get("data", {}) or {}
        raise XhsResponseError(data.get("code", -1), data.get("msg", ""), uri)
