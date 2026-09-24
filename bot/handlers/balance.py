from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo import UserRepo
from bot.keyboards.kb import balance_kb
from bot.services.partner_api import PartnerAPIClient, PartnerAPIError
from bot.utils.formatting import format_price

logger = structlog.get_logger()

router = Router(name="balance")


@router.message(F.text == "💰 Мой баланс")
async def show_balance(
    message: Message,
    db_user: User,
) -> None:
    await message.answer(
        f"💰 <b>Ваш баланс</b>\n\n"
        f"Баланс: <b>{format_price(db_user.balance_rub)}</b>\n\n"
        f"Для пополнения нажмите кнопку ниже.",
        parse_mode="HTML",
        reply_markup=balance_kb(),
    )

