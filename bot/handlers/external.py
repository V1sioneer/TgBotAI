from __future__ import annotations

import re

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import OrderType, User
from bot.keyboards.kb import confirm_external_kb, premium_months_kb
from bot.services.orders import InsufficientUserBalance, OrderService
from bot.services.partner_api import PartnerAPIClient, PartnerAPIError
from bot.services.pricing import calculate_user_price
from bot.utils.formatting import format_price

logger = structlog.get_logger()

router = Router(name="external")

USERNAME_RE = re.compile(r"^@[a-zA-Z][a-zA-Z0-9_]{3,31}$")


class TelegramBuyState(StatesGroup):
    waiting_username = State()


# ── Entry point ──────────────────────────────────────────────────────


@router.message(F.text == "💎 Telegram Premium")
async def show_telegram_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(TelegramBuyState.waiting_username)
    await state.update_data(item_type="premium")
    await message.answer(
        "💎 <b>Покупка Telegram Premium</b>\n\n"
        "Введите username получателя (например, @durov):",
        parse_mode="HTML",
    )


# ── Username input ───────────────────────────────────────────────────


@router.message(TelegramBuyState.waiting_username)
async def process_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username.startswith("@"):
        username = "@" + username

    if not USERNAME_RE.match(username):
        await message.answer(
            "❌ Неверный формат username. Введите в формате @username:"
        )
        return

    await state.clear()
    await message.answer(
        f"💎 <b>Telegram Premium для {username}</b>\n\n"
        f"Выберите срок подписки:",
        parse_mode="HTML",
        reply_markup=premium_months_kb(),
    )
    # save username in state
    await state.update_data(username=username)



# ── Premium months ───────────────────────────────────────────────────


@router.callback_query(F.data.startswith("premium_months:"))
async def cb_premium_months(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    months = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    data = await state.get_data()
    username = data.get("username", "?")
    await state.clear()

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💎 <b>Подтверждение</b>\n\n"
        f"Получатель: {username}\n"
        f"Срок: {months} мес.\n\n"
        f"Цена будет рассчитана при оформлении.\n"
        f"Подтвердить?",
        parse_mode="HTML",
        reply_markup=confirm_external_kb("premium", f"{username}:{months}"),
    )
    await callback.answer()


# ── Confirm external purchase ────────────────────────────────────────


@router.callback_query(F.data.startswith("confirm_ext:"))
async def cb_confirm_external(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    api: PartnerAPIClient,
    markup_percent: float,
    admin_ids: list[int],
) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    action = parts[1]  # premium | steam | game
    params_str = ":".join(parts[2:])

    svc = OrderService(session, api, markup_percent)

    try:
        if action == "premium":
            username, months_s = params_str.rsplit(":", 1)
            months = int(months_s)
            api_call = api.buy_telegram("premium", username, months)
            product_name = f"Premium {months} мес. → {username}"

            try:
                ext_result = await api_call
            except PartnerAPIError as exc:
                await _handle_api_error(callback, exc, db_user, admin_ids)
                return

            partner_price = ext_result.price
            user_price = calculate_user_price(partner_price, markup_percent)

            user = await svc.users.get(db_user.id)
            if user is None or user.balance_rub < user_price:
                await callback.message.edit_text(  # type: ignore[union-attr]
                    f"❌ Недостаточно средств. Нужно {format_price(user_price)}."
                )
                await callback.answer()
                return

            local_order = await svc.orders.create(
                user_id=db_user.id,
                order_type=OrderType.TELEGRAM,
                partner_price=partner_price,
                user_price=user_price,
                payload={"item_type": "premium", "username": username, "amount": months},
                status="processing",
            )
            await svc.users.update_balance(db_user.id, -user_price)
            await svc.txns.create(
                user_id=db_user.id,
                delta=-user_price,
                reason=product_name,
                order_id=local_order.id,
            )
            await svc.orders.update_status(
                local_order.id, "processing",
                partner_order_id=ext_result.order_id,
            )
            await session.commit()

            await callback.message.edit_text(  # type: ignore[union-attr]
                f"🔄 <b>Заказ оформлен!</b>\n\n"
                f"Тип: {product_name}\n"
                f"Списано: {format_price(user_price)}\n"
                f"Заказ #{ext_result.order_id}\n\n"
                f"Статус: в обработке. Вы получите уведомление.",
                parse_mode="HTML",
            )

        elif action == "steam":
            login, amount_s = params_str.rsplit(":", 1)
            amount_rub = float(amount_s)
            product_name = f"Steam {int(amount_rub)}₽ → {login}"

            try:
                ext_result = await api.buy_steam(login, amount_rub)
            except PartnerAPIError as exc:
                await _handle_api_error(callback, exc, db_user, admin_ids)
                return

            partner_price = ext_result.price
            user_price = calculate_user_price(partner_price, markup_percent)

            user = await svc.users.get(db_user.id)
            if user is None or user.balance_rub < user_price:
                await callback.message.edit_text(  # type: ignore[union-attr]
                    f"❌ Недостаточно средств. Нужно {format_price(user_price)}."
                )
                await callback.answer()
                return

            local_order = await svc.orders.create(
                user_id=db_user.id,
                order_type=OrderType.STEAM,
                partner_price=partner_price,
                user_price=user_price,
                payload={"login": login, "amount_rub": amount_rub},
                status="processing",
            )
            await svc.users.update_balance(db_user.id, -user_price)
            await svc.txns.create(
                user_id=db_user.id,
                delta=-user_price,
                reason=product_name,
                order_id=local_order.id,
            )
            await svc.orders.update_status(
                local_order.id, "processing",
                partner_order_id=ext_result.order_id,
            )
            await session.commit()

            await callback.message.edit_text(  # type: ignore[union-attr]
                f"🔄 <b>Заказ оформлен!</b>\n\n"
                f"Тип: {product_name}\n"
                f"Списано: {format_price(user_price)}\n"
                f"Заказ #{ext_result.order_id}\n\n"
                f"Статус: в обработке. Вы получите уведомление.",
                parse_mode="HTML",
            )

        else:
            await callback.message.edit_text("⚠️ Неизвестное действие.")  # type: ignore[union-attr]

    except InsufficientUserBalance as exc:
        await callback.message.edit_text(f"❌ {exc}")  # type: ignore[union-attr]

    await callback.answer()


async def _handle_api_error(
    callback: CallbackQuery,
    exc: PartnerAPIError,
    db_user: User,
    admin_ids: list[int],
) -> None:
    if exc.http_status == 503:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "⚠️ Этот раздел временно недоступен. Попробуйте позже."
        )
    elif exc.code == "INSUFFICIENT_BALANCE":
        await callback.message.edit_text(  # type: ignore[union-attr]
            "⚠️ Временно недоступно, попробуйте позже."
        )
        bot = callback.bot
        for aid in admin_ids:
            try:
                await bot.send_message(  # type: ignore[union-attr]
                    aid,
                    f"🚨 <b>INSUFFICIENT_BALANCE</b>\n"
                    f"Пользователь: {db_user.id} (@{db_user.username})",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    else:
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"⚠️ Ошибка: {exc.message}"
        )
    await callback.answer()
