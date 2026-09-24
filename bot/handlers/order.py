from __future__ import annotations

import re

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.keyboards.kb import confirm_external_kb, steam_games_menu_kb
from bot.services.partner_api import PartnerAPIClient
from bot.utils.formatting import format_price

logger = structlog.get_logger()

router = Router(name="order")

STEAM_LOGIN_RE = re.compile(r"^[a-zA-Z0-9_]{2,64}$")


class SteamBuyState(StatesGroup):
    waiting_login = State()
    waiting_amount = State()


class GameBuyState(StatesGroup):
    waiting_variation_id = State()


# ── Entry point ──────────────────────────────────────────────────────


@router.message(F.text == "🎮 Steam / Игры")
async def show_steam_menu(message: Message) -> None:
    await message.answer(
        "🎮 <b>Steam и Игры</b>\n\n"
        "Выберите раздел:",
        parse_mode="HTML",
        reply_markup=steam_games_menu_kb(),
    )


# ── Steam topup ──────────────────────────────────────────────────────


@router.callback_query(F.data == "steam_topup")
async def cb_steam_topup(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SteamBuyState.waiting_login)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>Пополнение Steam</b>\n\n"
        "Введите логин Steam:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SteamBuyState.waiting_login)
async def process_steam_login(
    message: Message,
    state: FSMContext,
) -> None:
    login = (message.text or "").strip()
    if not STEAM_LOGIN_RE.match(login):
        await message.answer("❌ Неверный формат логина Steam. Попробуйте ещё:")
        return

    await state.update_data(login=login)
    await state.set_state(SteamBuyState.waiting_amount)
    await message.answer(
        f"Логин: <b>{login}</b>\n\n"
        f"Введите сумму пополнения в рублях (от 100 до 15000):",
        parse_mode="HTML",
    )


@router.message(SteamBuyState.waiting_amount)
async def process_steam_amount(
    message: Message,
    state: FSMContext,
    steam_min_amount: int,
    steam_max_amount: int,
    markup_percent: float,
) -> None:
    text = (message.text or "").strip()
    try:
        amount = float(text)
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    if amount < steam_min_amount or amount > steam_max_amount:
        await message.answer(
            f"❌ Сумма должна быть от {steam_min_amount} до {steam_max_amount} ₽."
        )
        return

    data = await state.get_data()
    login = data["login"]
    await state.clear()

    await message.answer(
        f"💳 <b>Подтверждение пополнения Steam</b>\n\n"
        f"Логин: {login}\n"
        f"Сумма: {int(amount)} ₽\n\n"
        f"Цена будет рассчитана при оформлении.\n"
        f"Подтвердить?",
        parse_mode="HTML",
        reply_markup=confirm_external_kb("steam", f"{login}:{int(amount)}"),
    )


# ── Games ────────────────────────────────────────────────────────────


@router.callback_query(F.data == "games_list")
async def cb_games_list(callback: CallbackQuery) -> None:
    # In MVP: show instructions for entering variation_id
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🎮 <b>Покупка игр</b>\n\n"
        "Для покупки игры введите ID варианта (variation_id).\n"
        "Узнать ID можно у администратора.\n\n"
        "Введите /buy_game &lt;variation_id&gt; для покупки.",
        parse_mode="HTML",
    )
    await callback.answer()
