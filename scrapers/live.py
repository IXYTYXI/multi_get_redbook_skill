"""Live-stream barrage (弹幕) capture — skeleton.

Planned approach: connect to the Xiaohongshu live-room WebSocket feed,
decode barrage / gift / enter events, and yield ``LiveBarrageInfo`` objects.
The actual protocol handling will be filled in later; this file defines the
public interface so that the CLI and downstream consumers can be wired up now.
"""
from typing import List, Optional, Callable

from models.data import LiveBarrageInfo


class LiveBarrageScraper:
    """Capture live-stream barrage messages from a Xiaohongshu room."""

    def __init__(self, browser=None):
        self.browser = browser

    async def connect(self, room_url: str) -> str:
        """Resolve *room_url* to a room ID and establish the live connection.

        Returns the resolved ``room_id``.
        """
        raise NotImplementedError("live connection not yet implemented")

    async def listen(
        self,
        room_url: str,
        duration: Optional[int] = None,
        on_message: Optional[Callable[[LiveBarrageInfo], None]] = None,
    ) -> List[LiveBarrageInfo]:
        """Listen for barrage messages and return them when done.

        Parameters
        ----------
        room_url:
            Full Xiaohongshu live-room URL.
        duration:
            Maximum seconds to listen. ``None`` means listen indefinitely
            (until interrupted or the stream ends).
        on_message:
            Optional callback invoked for every incoming message (useful for
            real-time console output).
        """
        raise NotImplementedError("live listening not yet implemented")

    async def disconnect(self) -> None:
        """Tear down the live connection and release resources."""
        raise NotImplementedError("live disconnection not yet implemented")
