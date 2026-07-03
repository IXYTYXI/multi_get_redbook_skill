# 小红书数据采集工具 — 使用指南

本指南面向**非技术人员**，一步一步教你如何使用小红书数据采集工具。

---

## 目录

1. [你能用这个工具做什么？](#你能用这个工具做什么)
2. [准备工作（首次使用，约 10 分钟）](#准备工作)
3. [登录小红书（首次 + 过期后）](#登录小红书)
4. [搜索笔记](#搜索笔记)
5. [搜索用户](#搜索用户)
6. [一键全流程采集](#一键全流程采集)
7. [查看单篇笔记详情](#查看单篇笔记详情)
8. [查看评论](#查看评论)
9. [查看作者主页](#查看作者主页)
10. [写入飞书多维表格（可选）](#写入飞书多维表格)
11. [常见问题](#常见问题)

---

## 你能用这个工具做什么？

| 功能 | 说明 |
|---|---|
| 笔记搜索 | 输入关键词，获取相关笔记列表（标题、作者、点赞/收藏/评论数） |
| 用户搜索 | 输入关键词，找到相关用户（粉丝数、笔记数） |
| 笔记详情 | 获取某篇笔记的完整内容、图片、视频、标签 |
| 评论采集 | 获取某篇笔记下的所有评论 |
| 作者主页 | 获取作者的粉丝数、关注数、发布的笔记列表 |
| 全流程采集 | 搜索 → 详情 → 评论 → 下载图片/视频 → 写入飞书表格 |

---

## 准备工作

> 只需做一次。以后直接从「登录小红书」开始。

### 第 1 步：确认你的电脑环境

你需要一台 **Windows 电脑**（有屏幕、有浏览器），因为登录小红书需要扫码。

### 第 2 步：安装 Python

1. 打开 https://www.python.org/downloads/
2. 下载最新版 Python（3.10 或更高）
3. 安装时 **务必勾选「Add Python to PATH」**
4. 安装完成后，打开命令提示符（按 `Win+R`，输入 `cmd`，回车），输入：
   ```
   python --version
   ```
   看到类似 `Python 3.12.x` 就说明安装成功。

### 第 3 步：下载工具代码

在命令提示符中输入：
```
git clone https://github.com/IXYTYXI/multi_get_redbook_skill
cd multi_get_redbook_skill
```

> 如果没有 git，也可以直接在浏览器打开上面的链接，点绿色的 `Code` → `Download ZIP`，解压后进入文件夹。

### 第 4 步：安装依赖

在命令提示符中（确保在 `multi_get_redbook_skill` 文件夹里），输入：
```
pip install -r requirements.txt
playwright install chromium
```

等待安装完成即可。第一次安装 Chromium 浏览器可能需要几分钟。

✅ 准备工作完成！

---

## 登录小红书

> 首次使用必须登录。之后 cookie 会自动保存，通常几天到几周内不需要重新登录。

在命令提示符中输入：
```
python main.py login
```

会弹出一个浏览器窗口，显示小红书页面。你有两种方式登录：

- **扫码登录**：用小红书 App 扫描页面上的二维码
- **手机号登录**：输入手机号，填短信验证码

登录成功后，命令行会显示：
```
✅ 检测到登录，Cookie 已保存到 cookies.json 和 .env。
```

浏览器窗口会自动关闭。以后运行其他命令时，工具会自动使用保存的登录信息。

> ⚠️ 如果登录过期了（工具报错或提示未登录），重新运行 `python main.py login` 即可。

---

## 搜索笔记

**功能**：输入关键词，搜索小红书笔记。

```
python main.py search "美食" -n 10
```

- `"美食"` — 替换成你想搜索的关键词
- `-n 10` — 最多返回 10 条结果（不写默认 20 条）

**输出示例**：
```
keyword='美食'  got 10 notes

 1. [normal] 这家餐厅必须安利！
    by 小美食家 | 赞4487 藏4469 评251
    id=6960cc86000000001a031d30 token=yes
 2. [video] 一分钟学会做糖醋排骨
    by 厨房日记 | 赞7931 藏404 评7720
    ...
```

每条结果包含：
- **类型**：`normal`（图文）或 `video`（视频）
- **标题**
- **作者**
- **点赞数、收藏数、评论数**
- **note_id 和 token**（后续查详情/评论时需要）

---

## 搜索用户

**功能**：按关键词搜索小红书用户/博主。

```
python main.py search-user "美食博主" -n 10
```

**输出示例**：
```
keyword='美食博主'  got 10 users

 1. 小厨娘
    fans=125000 notes=342
    desc: 每天分享家常菜做法
    id=5a3b2c1d...
```

---

## 一键全流程采集

**功能**：搜索 → 获取详情 → 获取评论 → 下载图片视频 → 写入飞书。这是最常用的命令。

```
python main.py scrape-all -k "护肤" -n 10
```

- `-k "护肤"` — 搜索关键词
- `-n 10` — 采集 10 篇笔记

**过程会显示每一步的进度**：
```
=== Step 1: Search notes for '护肤' (max 10) ===
  Found 10 notes

=== Step 2: Get detail for 10 notes ===
  [1/10] 6960cc86... '这个面霜真的绝了'
    → desc=235c images=4 video=no tags=护肤, 面霜
  ...

=== Step 3: Get comments for 10 notes ===
  [1/10] 6960cc86... (comments: 251)
    → got 50 comments
  ...

=== Step 4: Write to Feishu ===
  Written 10/10 note records
  Written 156/156 comment records

=== Done ===
  Notes: 10, Comments: 156
```

> 如果没有配置飞书，数据会在命令行以摘要形式展示，不会丢失。

### 跳过某些步骤

如果你只需要部分数据，可以设置环境变量跳过：

**Windows 命令提示符**：
```
set SKIP_COMMENTS=true
python main.py scrape-all -k "护肤" -n 10
```

**PowerShell**：
```
$env:SKIP_COMMENTS="true"
python main.py scrape-all -k "护肤" -n 10
```

可跳过的步骤：
- `SKIP_DETAIL=true` — 跳过笔记详情（只要搜索列表数据）
- `SKIP_COMMENTS=true` — 跳过评论
- `SKIP_MEDIA=true` — 跳过图片/视频下载和上传

---

## 查看单篇笔记详情

**功能**：获取某篇笔记的完整信息。

你需要笔记的 `note_id` 和 `xsec_token`（从搜索结果中获取）：

```
python main.py note 6960cc86000000001a031d30 "ABJ8FFjuxDL3qR1tJr/s..."
```

**输出**：
```
Title:   这个面霜真的绝了
Author:  护肤小达人
Type:    normal
Likes:   4487  Collects: 4469  Comments: 251
Tags:    护肤, 面霜, 好物推荐
Video:   N/A
Images:  4
Desc:    最近入手了这款面霜...
```

---

## 查看评论

**功能**：获取某篇笔记的评论。

```
python main.py comment 6960cc86000000001a031d30 "ABJ8FFjuxDL3qR1tJr/s..." -n 20
```

- `-n 20` — 最多获取 20 条评论

**输出**：
```
note_id=6960cc86...  got 20 comments

 1. [小红薯用户] 这个真的好用吗？
    likes=12 replies=3 time=2025-06-15 14:30:22
 2. [护肤达人] 已入手，确实不错
    likes=5 replies=0 time=2025-06-15 16:45:11
 ...
```

---

## 查看作者主页

**功能**：获取作者的基本信息和发布的笔记。

```
python main.py user 5a3b2c1d... --notes
```

- `--notes` — 加上这个参数会同时获取作者发布的笔记列表
- 不加 `--notes` 只看基本信息

**输出**：
```
Nickname:  护肤小达人
Fans:      125000
Follows:   342
Notes:     89
Desc:      分享日常护肤心得

--- User notes (30) ---
 1. 这个面霜真的绝了  likes=4487
 2. 平价好用的防晒推荐  likes=2301
 ...
```

---

## 写入飞书多维表格

如果你想把采集的数据自动写入飞书多维表格，需要额外配置。

### 第 1 步：创建飞书应用

1. 打开 https://open.feishu.cn/app ，登录你的飞书账号
2. 点「创建自建应用」
3. 在应用的「权限管理」中，添加以下权限：
   - `bitable:app` — 多维表格
   - `drive:drive` — 云文档（用于上传图片/视频附件）
4. 记下 **App ID** 和 **App Secret**

### 第 2 步：创建多维表格

1. 在飞书中创建一个多维表格
2. 创建两个数据表：
   - **笔记表** — 用来存笔记数据
   - **评论表** — 用来存评论数据
3. 不需要手动建字段，工具会自动写入
4. 记下多维表格的 **App Token**（在表格 URL 中，`/base/` 后面那串字符）
5. 记下两个数据表的 **Table ID**（点表名旁边的 `⋮` → 「复制链接」，URL 中 `table=` 后面的值）

### 第 3 步：配置环境变量

在 `multi_get_redbook_skill` 文件夹中，复制 `.env.example` 为 `.env`：
```
copy .env.example .env
```

用记事本打开 `.env`，填入你的信息：
```
FEISHU_APP_ID=你的App ID
FEISHU_APP_SECRET=你的App Secret
FEISHU_APP_TOKEN=你的多维表格App Token
NOTE_TABLE_ID=笔记表的Table ID
COMMENT_TABLE_ID=评论表的Table ID
```

保存后，运行 `scrape-all` 时数据就会自动写入飞书了。

---

## 常见问题

### Q: 报错「Not logged in」或「Login timeout」
**A**: 登录已过期。重新运行 `python main.py login`，扫码登录即可。

### Q: 搜索不到结果
**A**: 小红书对频繁访问有风控。等几分钟再试，或换一个关键词。也可能是关键词太冷门。

### Q: 笔记详情拿到了但点赞数是 0
**A**: 少数情况下小红书的页面数据结构不同。工具会自动尝试多种提取方式（SSR 数据 → DOM 页面元素），但偶尔仍可能失败。搜索结果中的互动数据通常是准确的。

### Q: 运行时弹出浏览器窗口
**A**: 正常的。工具使用真实浏览器来访问小红书（避免被识别为爬虫）。窗口会在操作完成后自动关闭，不需要手动操作。

### Q: 想只采集笔记不要评论
**A**: 设置环境变量 `SKIP_COMMENTS=true`（见「跳过某些步骤」一节）。

### Q: 飞书写入报错
**A**: 检查以下几点：
1. App ID / App Secret 是否正确
2. 飞书应用是否已发布（不是草稿状态）
3. 多维表格是否已给你的飞书应用授权（在表格设置 → 自动化 → API 访问中添加应用）

### Q: 可以定时自动采集吗？
**A**: 可以配合 Multica 的 Autopilot 功能实现定时触发，但需要确保 cookie 不过期。建议配合桌面 runtime 使用，过期时会自动弹窗让你重新扫码。

---

## 命令速查表

| 命令 | 用途 |
|---|---|
| `python main.py check` | 测试工具是否安装正确 |
| `python main.py login` | 登录小红书（扫码） |
| `python main.py search "关键词" -n 数量` | 搜索笔记 |
| `python main.py search-user "关键词" -n 数量` | 搜索用户 |
| `python main.py note <id> <token>` | 查看笔记详情 |
| `python main.py comment <id> <token> -n 数量` | 查看评论 |
| `python main.py user <id> --notes` | 查看作者主页和笔记 |
| `python main.py scrape-all -k "关键词" -n 数量` | 全流程采集 |
