from __future__ import annotations

import math

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo import OrderRepo
from bot.keyboards.kb import history_page_kb
from bot.utils.formatting import format_datetime, format_price, format_status

logger = structlog.get_logger()

router = Router(name="history")

ORDERS_PER_PAGE = 5


@router.message(F.text == "📜 История")
async def show_history(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> None:
    repo = OrderRepo(session)
    total = await repo.count_user_orders(db_user.id)
    if total == 0:
        await message.answer("📭 У вас пока нет заказов.")
        return

    total_pages = max(1, math.ceil(total / ORDERS_PER_PAGE))
    orders = await repo.get_user_orders(db_user.id, limit=ORDERS_PER_PAGE, offset=0)

    text = _build_history_text(orders, 0, total_pages)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=history_page_kb(0, total_pages),
    )


@router.callback_query(F.data.startswith("history_page:"))
async def cb_history_page(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    page = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    repo = OrderRepo(session)
    total = await repo.count_user_orders(db_user.id)
    total_pages = max(1, math.ceil(total / ORDERS_PER_PAGE))
    page = min(page, total_pages - 1)

    orders = await repo.get_user_orders(
        db_user.id, limit=ORDERS_PER_PAGE, offset=page * ORDERS_PER_PAGE
    )

    text = _build_history_text(orders, page, total_pages)
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        parse_mode="HTML",
        reply_markup=history_page_kb(page, total_pages),
    )
    await callback.answer()


def _build_history_text(orders, page: int, total_pages: int) -> str:
    lines = [f"📜 <b>История заказов</b> (стр. {page + 1}/{total_pages})\n"]
    for o in orders:
        status_str = format_status(o.status)
        type_labels = {
            "catalog": "📦 Каталог",
            "telegram": "💎 TG Premium",
            "steam": "🎮 Steam",
            "game": "🎮 Игра",
        }
        type_label = type_labels.get(o.type.value if hasattr(o.type, 'value') else o.type, o.type)

        line = (
            f"\n{'─' * 20}\n"
            f"#{o.id} | {type_label}\n"
            f"Сумма: {format_price(o.user_price)}\n"
            f"Статус: {status_str}\n"
            f"Дата: {format_datetime(o.created_at)}"
        )
        if o.delivered_data and o.status.value == "success":
            line += f"\n🔑 <code>{o.delivered_data[:50]}</code>"
        lines.append(line)

    return "\n".join(lines)
