from dataclasses import dataclass, asdict


@dataclass
class NoteInfo:
    """A Xiaohongshu note (图文 or video). ``xsec_token`` / ``xsec_source`` are
    obtained from the search/list response and MUST be carried into the
    note-detail and comment requests — a bare note_id cannot be resolved."""

    note_id: str = ""
    xsec_token: str = ""
    xsec_source: str = ""
    note_type: str = ""  # "normal" (图文) | "video"
    title: str = ""
    desc: str = ""
    author_nickname: str = ""
    author_user_id: str = ""
    liked_count: int = 0
    collected_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    create_time: str = ""
    cover_url: str = ""
    video_url: str = ""
    image_urls: str = ""  # comma-separated
    note_url: str = ""
    tags: str = ""  # comma-separated

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class XhsUserInfo:
    user_id: str = ""
    xsec_token: str = ""
    nickname: str = ""
    desc: str = ""
    fans: int = 0
    follows: int = 0
    interaction: int = 0  # 获赞与收藏
    note_count: int = 0
    avatar_url: str = ""
    homepage_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CommentInfo:
    comment_id: str = ""
    note_id: str = ""
    parent_comment_id: str = ""
    reply_to_nickname: str = ""
    reply_to_user_id: str = ""
    content: str = ""
    user_nickname: str = ""
    user_id: str = ""
    like_count: int = 0
    sub_comment_count: int = 0
    create_time: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LiveBarrageInfo:
    """A single message captured from a Xiaohongshu live-stream chat."""

    user_id: str = ""
    user_name: str = ""
    content: str = ""
    message_type: str = ""  # "barrage" | "gift" | "enter" | "follow" | "like" | "unknown"
    timestamp: str = ""
    room_id: str = ""
    room_url: str = ""
    raw_data: str = ""  # JSON string of the original protocol payload

    def to_dict(self) -> dict:
        return asdict(self)
