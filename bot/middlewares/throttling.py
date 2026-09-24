from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update


class ThrottlingMiddleware(BaseMiddleware):
    """Anti-flood: 1 action per second per user."""

    def __init__(self, cooldown: float = 1.0) -> None:
        self.cooldown = cooldown
        self._last: Dict[int, float] = defaultdict(float)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        uid = user.id
        now = time.monotonic()
        if now - self._last[uid] < self.cooldown:
            # Silently drop the event
            return None
        self._last[uid] = now
        return await handler(event, data)
