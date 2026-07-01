# multi_get_redbook_skill (xhs-scraper)

Self-built Multica skill to scrape Xiaohongshu (小红书 / RED) — note search, author
profile, note details, comments — and write to Feishu bitable or local json/csv.
Mirrors the existing `douyin-scraper` architecture, adapted for Xiaohongshu.
**Independent implementation; it does not reuse the third-party MediaCrawler fork's
code** (that project is a validated reference for the signing *approach* only).

See `SKILL.md` for the full status table, prerequisites, and architecture.

## Install

```bash
pip install -r requirements.txt
playwright install chromium
python main.py check          # -> "xhs-scraper scaffold OK" (offline, no login)
```

## Cookie 设置（用户的核心步骤）

小红书**每个 web 接口都需要登录态 + 签名**，没有 Cookie 就抓不到数据。两种方式，任选其一：

### 方式 A：扫码登录，自动保存（推荐）

```bash
python main.py login
```

弹出可见浏览器，扫码登录 `xiaohongshu.com`。检测到登录（`web_session` 写入）后，
自动把整份会话保存到 **`cookies.json`**（Playwright cookie 数组）并镜像成 `.env` 的
`XHS_COOKIE`。之后抓取会自动加载 `cookies.json`。两个文件都已 gitignore。

### 方式 B：手动设置 `XHS_COOKIE`

1. Chrome 打开 <https://www.xiaohongshu.com> 并扫码登录
2. `F12` → **Network(网络)** 面板 → 刷新 → 点任意一条 `xiaohongshu.com` 请求
3. 在 **Request Headers** 里找到 `Cookie:`，**整行复制**它的值（不含 `Cookie:` 前缀）
4. 在 Multica 里通过 agent 的 custom_env 注入 `XHS_COOKIE`，或写进本地 `.env`

> `cookies.json` 优先于 `XHS_COOKIE`。**关键字段：`a1`（设备指纹）、`web_session`
> （登录后才写入，是登录态的主要标志）。** 未登录 / 过期时 `search` 等命令会**明确报错**
> （缺少 `web_session` / `a1`），不会静默返回空。**切勿把 Cookie 贴进 issue 评论，建议用小号。**

## 抓取命令

```bash
python main.py search "护肤" -n 30                 # 关键词搜笔记
python main.py search "护肤" --detail --comments   # 附带完整详情 + 评论
python main.py note   <note_id> <xsec_token>       # 单篇笔记详情
python main.py comment <note_id> <xsec_token> -n 100
python main.py user   <user_id> --xsec-token <t>   # 作者主页 + 笔记
```

- 配了 `FEISHU_APP_ID` + 对应 `*_TABLE_ID` 就写飞书多维表格；否则（或加 `--local`）落到
  `output/*.json` + `*.csv`。
- `--no-headless` 用可见浏览器（过验证码时）。
- 搜索/列表返回的 `xsec_token` 会自动透传到详情/评论请求（否则触发风控 `300017`）。

## 签名机制（x-s / x-t / x-s-common）

不手写混淆算法：在**已登录页面内**调用小红书自己的签名函数（`window._webmsxyw`）拿到
`x-s` / `x-t`，Python 侧用 `a1`（Cookie）+ `b1`（localStorage）组装 `x-s-common`
信封（`core/sign.py`）。好处是每次小红书更新签名器，页面仍然暴露它，`x-s/x-t` 自动跟进。

**已知限制 / 需用户配合联调：** `x-s-common` 的版本常量与 `x9` 校验值只能对着
**真实登录会话**验证，而登录态只能由用户本人提供。若接口返回风控码 `300012/300015`，
客户端会抛出带说明的 `XhsResponseError`，据此微调 `core/sign.py` 里的常量即可；
`x-s/x-t` 来自页面本身，不受影响。

## Status

- ✅ Stage 0 — scaffold, reused storage/downloader/date-filter, data models
- ✅ Stage 1 — browser-injection signing (`core/sign.py`)（需登录 Cookie 联调验证）
- ✅ Stage 2 — scrapers（search / note / comment / user，`xsec_token` 透传，解析已离线测试）
- ✅ Stage 3 — signed client、Feishu / 本地输出、各命令编排
- ✅ Stage 4 — 文档 / 已知限制（本文件 + `SKILL.md`）
