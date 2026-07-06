import httpx
import os
import zlib
from typing import List
from config.settings import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_APP_TOKEN,
    FEISHU_TABLE_ID,
    FEISHU_API_BASE,
)


class FeishuBitable:
    """Write data to Feishu multidimensional tables (Bitable).

    Reused verbatim from douyin-scraper (our own code); only the record
    converters and table schemas below are adapted to Xiaohongshu fields.
    """

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        app_token: str = "",
        table_id: str = "",
    ):
        self.app_id = app_id or FEISHU_APP_ID
        self.app_secret = app_secret or FEISHU_APP_SECRET
        self.app_token = app_token or FEISHU_APP_TOKEN
        self.table_id = table_id or FEISHU_TABLE_ID
        self._tenant_token: str = ""
        self._client = httpx.Client(timeout=30.0)

    def _get_tenant_token(self) -> str:
        if self._tenant_token:
            return self._tenant_token
        url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
        resp = self._client.post(
            url, json={"app_id": self.app_id, "app_secret": self.app_secret}
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"Failed to get Feishu token: {data.get('msg', 'unknown error')}"
            )
        self._tenant_token = data["tenant_access_token"]
        return self._tenant_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_tenant_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def list_tables(self) -> list:
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables"
        resp = self._client.get(url, headers=self._headers())
        data = resp.json()
        if data.get("code") != 0:
            print(f"[Feishu] List tables error: {data.get('msg')}")
            return []
        items = data.get("data", {}).get("items", [])
        return [{"table_id": t["table_id"], "name": t.get("name", "")} for t in items]

    def find_table_by_name(self, name: str) -> str:
        for t in self.list_tables():
            if t["name"] == name:
                return t["table_id"]
        return ""

    def create_table(self, name: str) -> str:
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables"
        resp = self._client.post(
            url, headers=self._headers(), json={"table": {"name": name}}
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to create table: {data.get('msg')}")
        table_id = data["data"]["table_id"]
        print(f"[Feishu] Created table '{name}' with ID: {table_id}")
        return table_id

    def ensure_table(self, table_id: str, name: str, setup_fn) -> str:
        if table_id:
            return table_id
        existing = self.find_table_by_name(name)
        if existing:
            print(f"[Feishu] Reusing existing table '{name}' ({existing})")
            return existing
        tid = self.create_table(name)
        setup_fn(tid)
        return tid

    def add_fields(self, fields: List[dict], table_id: str = "") -> None:
        tid = table_id or self.table_id
        for f in fields:
            url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables/{tid}/fields"
            resp = self._client.post(url, headers=self._headers(), json=f)
            data = resp.json()
            if data.get("code") != 0:
                print(f"[Feishu] Add field '{f.get('field_name')}' error: {data.get('msg')}")

    def write_records(self, records: List[dict], table_id: str = "") -> int:
        tid = table_id or self.table_id
        total_written = 0
        for i in range(0, len(records), 500):
            batch = records[i : i + 500]
            url = (
                f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}"
                f"/tables/{tid}/records/batch_create"
            )
            payload = {"records": [{"fields": r} for r in batch]}
            resp = self._client.post(url, headers=self._headers(), json=payload)
            data = resp.json()
            if data.get("code") != 0:
                print(
                    f"[Feishu] Batch write error (batch {i // 500 + 1}): {data.get('msg')}"
                )
            else:
                total_written += len(data.get("data", {}).get("records", []))
        print(f"[Feishu] Written {total_written}/{len(records)} records to table {tid}")
        return total_written

    def setup_note_table(self, table_id: str = "") -> None:
        fields = [
            {"field_name": "作者", "type": 1},
            {"field_name": "标题", "type": 1},
            {"field_name": "正文", "type": 1},
            {"field_name": "笔记链接", "type": 15},
            {"field_name": "封面", "type": 15},
            {"field_name": "图片", "type": 1},
            {"field_name": "视频", "type": 15},
            {"field_name": "类型", "type": 1},
            {"field_name": "点赞数", "type": 2},
            {"field_name": "收藏数", "type": 2},
            {"field_name": "评论数", "type": 2},
            {"field_name": "分享数", "type": 2},
            {"field_name": "发布时间", "type": 1},
            {"field_name": "话题标签", "type": 1},
            {"field_name": "封面附件", "type": 17},
            {"field_name": "视频附件", "type": 17},
            {"field_name": "图片附件", "type": 17},
        ]
        self.add_fields(fields, table_id)

    def setup_user_table(self, table_id: str = "") -> None:
        fields = [
            {"field_name": "用户ID", "type": 1},
            {"field_name": "昵称", "type": 1},
            {"field_name": "简介", "type": 1},
            {"field_name": "粉丝数", "type": 2},
            {"field_name": "关注数", "type": 2},
            {"field_name": "获赞与收藏", "type": 2},
            {"field_name": "笔记数", "type": 2},
            {"field_name": "主页链接", "type": 15},
        ]
        self.add_fields(fields, table_id)

    def setup_comment_table(self, table_id: str = "") -> None:
        fields = [
            {"field_name": "评论ID", "type": 1},
            {"field_name": "笔记ID", "type": 1},
            {"field_name": "父评论ID", "type": 1},
            {"field_name": "回复对象", "type": 1},
            {"field_name": "回复对象ID", "type": 1},
            {"field_name": "评论内容", "type": 1},
            {"field_name": "用户昵称", "type": 1},
            {"field_name": "用户ID", "type": 1},
            {"field_name": "点赞数", "type": 2},
            {"field_name": "回复数", "type": 2},
            {"field_name": "发布时间", "type": 1},
        ]
        self.add_fields(fields, table_id)

    def upload_file(self, file_path: str, parent_type: str = "bitable_image") -> str:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        token = self._get_tenant_token()
        if file_size <= 20 * 1024 * 1024:
            return self._upload_small(file_path, file_name, file_size, parent_type, token)
        return self._upload_chunked(file_path, file_name, file_size, parent_type, token)

    def _upload_small(self, file_path, file_name, file_size, parent_type, token):
        headers = {"Authorization": f"Bearer {token}"}
        with open(file_path, "rb") as f:
            resp = self._client.post(
                f"{FEISHU_API_BASE}/drive/v1/medias/upload_all",
                headers=headers,
                data={
                    "file_name": file_name,
                    "parent_type": parent_type,
                    "parent_node": self.app_token,
                    "size": str(file_size),
                },
                files={"file": (file_name, f, "application/octet-stream")},
            )
        data = resp.json()
        if data.get("code") != 0:
            print(f"[Feishu] Upload error: {data.get('msg')}")
            return ""
        return data.get("data", {}).get("file_token", "")

    def _upload_chunked(self, file_path, file_name, file_size, parent_type, token):
        headers_json = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        headers_upload = {"Authorization": f"Bearer {token}"}
        resp = self._client.post(
            f"{FEISHU_API_BASE}/drive/v1/medias/upload_prepare",
            headers=headers_json,
            json={
                "file_name": file_name,
                "parent_type": parent_type,
                "parent_node": self.app_token,
                "size": file_size,
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            print(f"[Feishu] Upload prepare error: {data.get('msg')}")
            return ""
        upload_id = data["data"]["upload_id"]
        block_size = data["data"]["block_size"]
        block_num = data["data"]["block_num"]
        with open(file_path, "rb") as f:
            for i in range(block_num):
                chunk = f.read(block_size)
                if not chunk:
                    break
                checksum = str(zlib.adler32(chunk) & 0xFFFFFFFF)
                resp = self._client.post(
                    f"{FEISHU_API_BASE}/drive/v1/medias/upload_part",
                    headers=headers_upload,
                    data={
                        "upload_id": upload_id,
                        "seq": str(i),
                        "size": str(len(chunk)),
                        "checksum": checksum,
                    },
                    files={"file": (f"part_{i}", chunk, "application/octet-stream")},
                    timeout=120.0,
                )
                d = resp.json()
                if d.get("code") != 0:
                    print(f"[Feishu] Upload part {i} error: {d.get('msg')}")
                    return ""
        resp = self._client.post(
            f"{FEISHU_API_BASE}/drive/v1/medias/upload_finish",
            headers=headers_json,
            json={"upload_id": upload_id, "block_num": block_num},
        )
        data = resp.json()
        if data.get("code") != 0:
            print(f"[Feishu] Upload finish error: {data.get('msg')}")
            return ""
        return data.get("data", {}).get("file_token", "")

    def close(self):
        self._client.close()


def note_to_feishu_record(note) -> dict:
    return {
        "作者": note.author_nickname,
        "标题": note.title,
        "正文": note.desc,
        "笔记链接": {"link": note.note_url, "text": "查看笔记"} if note.note_url else "",
        "封面": {"link": note.cover_url, "text": "封面"} if note.cover_url else "",
        "图片": note.image_urls or "",
        "视频": {"link": note.video_url, "text": "播放视频"} if note.video_url else "",
        "类型": note.note_type,
        "点赞数": note.liked_count,
        "收藏数": note.collected_count,
        "评论数": note.comment_count,
        "分享数": note.share_count,
        "发布时间": note.create_time,
        "话题标签": note.tags,
    }


def user_to_feishu_record(user) -> dict:
    return {
        "用户ID": user.user_id,
        "昵称": user.nickname,
        "简介": user.desc,
        "粉丝数": user.fans,
        "关注数": user.follows,
        "获赞与收藏": user.interaction,
        "笔记数": user.note_count,
        "主页链接": {"link": user.homepage_url, "text": user.nickname} if user.homepage_url else "",
    }


def comment_to_feishu_record(comment) -> dict:
    return {
        "评论ID": comment.comment_id,
        "笔记ID": comment.note_id,
        "父评论ID": comment.parent_comment_id,
        "回复对象": comment.reply_to_nickname,
        "回复对象ID": comment.reply_to_user_id,
        "评论内容": comment.content,
        "用户昵称": comment.user_nickname,
        "用户ID": comment.user_id,
        "点赞数": comment.like_count,
        "回复数": comment.sub_comment_count,
        "发布时间": comment.create_time,
    }
