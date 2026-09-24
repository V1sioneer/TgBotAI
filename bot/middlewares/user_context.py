from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from bot.db.repo import UserRepo


class UserContextMiddleware(BaseMiddleware):
    """Ensure DB user exists and inject session + user into handler data."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        async with self._session_factory() as session:
            repo = UserRepo(session)
            db_user = await repo.get_or_create(
                user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
            await session.commit()

            data["session"] = session
            data["db_user"] = db_user
            result = await handler(event, data)
            return result
