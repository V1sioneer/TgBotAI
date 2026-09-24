from __future__ import annotations

import math

import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repo import DepositRepo, TransactionRepo, UserRepo
from bot.services.payments import CryptoBotPayment, YooKassaPayment
from bot.utils.formatting import format_price

logger = structlog.get_logger()

router = Router(name="payment")

TOPUP_AMOUNTS = [100, 250, 500, 1000, 2500, 5000]


class TopupState(StatesGroup):
    waiting_amount = State()


# ── Entry point (from balance handler) ───────────────────────────────


@router.callback_query(F.data == "topup_balance")
async def cb_topup_balance(callback: CallbackQuery) -> None:
    buttons = []
    row = []
    for i, amt in enumerate(TOPUP_AMOUNTS):
        row.append(
            InlineKeyboardButton(
                text=f"{amt} ₽", callback_data=f"topup_amount:{amt}"
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text="✏️ Своя сумма", callback_data="topup_custom"
        )
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")
    ])

    await callback.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>Пополнение баланса</b>\n\n"
        "Выберите сумму:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ── Custom amount ────────────────────────────────────────────────────


@router.callback_query(F.data == "topup_custom")
async def cb_topup_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TopupState.waiting_amount)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "✏️ Введите сумму пополнения в рублях (от 50 до 50000):"
    )
    await callback.answer()


@router.message(TopupState.waiting_amount)
async def process_topup_amount(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        amount = float(text)
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    if amount < 50 or amount > 50000:
        await message.answer("❌ Сумма от 50 до 50000 ₽.")
        return

    amount = math.ceil(amount)
    await state.clear()
    await _show_payment_methods(message, amount)


# ── Amount selected ──────────────────────────────────────────────────


@router.callback_query(F.data.startswith("topup_amount:"))
async def cb_topup_amount(callback: CallbackQuery) -> None:
    amount = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    await _show_payment_methods_edit(callback, amount)
    await callback.answer()


async def _show_payment_methods(message: Message, amount: int) -> None:
    kb = _payment_methods_kb(amount)
    await message.answer(
        f"💳 <b>Пополнение на {format_price(amount)}</b>\n\n"
        f"Выберите способ оплаты:",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def _show_payment_methods_edit(callback: CallbackQuery, amount: int) -> None:
    kb = _payment_methods_kb(amount)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💳 <b>Пополнение на {format_price(amount)}</b>\n\n"
        f"Выберите способ оплаты:",
        parse_mode="HTML",
        reply_markup=kb,
    )


def _payment_methods_kb(amount: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="🤖 CryptoBot (крипта)",
                callback_data=f"pay_crypto:{amount}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⭐ Telegram Stars",
                callback_data=f"pay_stars:{amount}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="💳 Карта / СБП (ЮKassa)",
                callback_data=f"pay_yookassa:{amount}",
            ),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="topup_balance"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══════════════════════════════════════════════════════════════════════
# CryptoBot
# ═══════════════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith("pay_crypto:"))
async def cb_pay_crypto(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    cryptobot: CryptoBotPayment | None,
) -> None:
    if not cryptobot:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "⚠️ CryptoBot не настроен. Обратитесь к администратору."
        )
        await callback.answer()
        return

    amount = int(callback.data.split(":")[1])  # type: ignore[union-attr]

    try:
        invoice = await cryptobot.create_invoice(
            amount=amount,
            description=f"Пополнение баланса на {amount} ₽",
            payload=f"{db_user.id}:{amount}",
        )
    except Exception as exc:
        logger.error("cryptobot_create_error", error=str(exc))
        await callback.message.edit_text(  # type: ignore[union-attr]
            "⚠️ Ошибка создания платежа. Попробуйте позже."
        )
        await callback.answer()
        return

    # Save deposit
    dep_repo = DepositRepo(session)
    await dep_repo.create(
        user_id=db_user.id,
        amount_rub=amount,
        method="cryptobot",
        external_id=str(invoice["invoice_id"]),
        pay_url=invoice["pay_url"],
    )
    await session.commit()

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"🤖 <b>Оплата через CryptoBot</b>\n\n"
        f"Сумма: <b>{format_price(amount)}</b>\n\n"
        f"Нажмите кнопку ниже для оплаты.\n"
        f"После оплаты баланс пополнится автоматически (до 1 мин).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💰 Оплатить", url=invoice["pay_url"])],
                [InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"check_crypto:{invoice['invoice_id']}:{amount}",
                )],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_crypto:"))
async def cb_check_crypto(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    cryptobot: CryptoBotPayment | None,
) -> None:
    if not cryptobot:
        await callback.answer("CryptoBot не настроен", show_alert=True)
        return

    parts = callback.data.split(":")  # type: ignore[union-attr]
    invoice_id = int(parts[1])
    amount = int(parts[2])

    try:
        invoice = await cryptobot.get_invoice(invoice_id)
    except Exception:
        await callback.answer("Ошибка проверки", show_alert=True)
        return

    if invoice["status"] == "paid":
        dep_repo = DepositRepo(session)
        dep = await dep_repo.get_by_external_id(str(invoice_id))
        if dep and dep.status == "pending":
            await dep_repo.mark_paid(dep.id)
            user_repo = UserRepo(session)
            new_balance = await user_repo.update_balance(db_user.id, amount)
            tx_repo = TransactionRepo(session)
            await tx_repo.create(
                user_id=db_user.id,
                delta=amount,
                reason=f"Пополнение CryptoBot #{invoice_id}",
            )
            await session.commit()

            await callback.message.edit_text(  # type: ignore[union-attr]
                f"✅ <b>Оплата получена!</b>\n\n"
                f"Зачислено: {format_price(amount)}\n"
                f"Баланс: {format_price(new_balance)}",
                parse_mode="HTML",
            )
        else:
            await callback.answer("✅ Уже зачислено!", show_alert=True)
    elif invoice["status"] == "expired":
        await callback.message.edit_text("❌ Счёт истёк. Создайте новый.")  # type: ignore[union-attr]
    else:
        await callback.answer("⏳ Оплата ещё не получена. Подождите.", show_alert=True)

    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════
# Telegram Stars ⭐
# ═══════════════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith("pay_stars:"))
async def cb_pay_stars(
    callback: CallbackQuery,
    db_user: User,
    stars_exchange_rate: float,
) -> None:
    amount_rub = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    stars_needed = math.ceil(amount_rub / stars_exchange_rate)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"⭐ <b>Оплата через Telegram Stars</b>\n\n"
        f"Сумма: <b>{format_price(amount_rub)}</b>\n"
        f"К оплате: <b>{stars_needed} ⭐</b>\n"
        f"(курс: 1 ⭐ = {stars_exchange_rate} ₽)\n\n"
        f"Нажмите кнопку ниже для оплаты:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"⭐ Оплатить {stars_needed} Stars",
                    callback_data=f"send_stars:{amount_rub}:{stars_needed}",
                )],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="topup_balance")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("send_stars:"))
async def cb_send_stars(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    amount_rub = int(parts[1])
    stars = int(parts[2])

    # Send Telegram Stars invoice
    await callback.message.answer_invoice(  # type: ignore[union-attr]
        title=f"Пополнение на {amount_rub} ₽",
        description=f"Пополнение баланса бота на {amount_rub} ₽",
        payload=f"stars:{amount_rub}",
        currency="XTR",
        prices=[LabeledPrice(label=f"Пополнение {amount_rub} ₽", amount=stars)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    """Always approve Stars pre-checkout."""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> None:
    """Handle successful Stars payment."""
    payment = message.successful_payment
    if not payment or not payment.invoice_payload.startswith("stars:"):
        return

    amount_rub = int(payment.invoice_payload.split(":")[1])

    # Credit balance
    dep_repo = DepositRepo(session)
    await dep_repo.create(
        user_id=db_user.id,
        amount_rub=amount_rub,
        method="stars",
        external_id=payment.telegram_payment_charge_id,
        status="paid",
    )

    user_repo = UserRepo(session)
    new_balance = await user_repo.update_balance(db_user.id, amount_rub)

    tx_repo = TransactionRepo(session)
    await tx_repo.create(
        user_id=db_user.id,
        delta=amount_rub,
        reason=f"Пополнение Stars ({payment.total_amount} ⭐)",
    )
    await session.commit()

    await message.answer(
        f"✅ <b>Оплата получена!</b>\n\n"
        f"Зачислено: {format_price(amount_rub)}\n"
        f"Баланс: {format_price(new_balance)}",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════════════
# YooKassa (карта / СБП)
# ═══════════════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith("pay_yookassa:"))
async def cb_pay_yookassa(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    yookassa: YooKassaPayment | None,
) -> None:
    if not yookassa:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "⚠️ Оплата картой/СБП временно недоступна."
        )
        await callback.answer()
        return

    amount = int(callback.data.split(":")[1])  # type: ignore[union-attr]

    try:
        payment = await yookassa.create_payment(
            amount=amount,
            description=f"Пополнение баланса на {amount} ₽",
            metadata={"user_id": str(db_user.id), "amount": str(amount)},
        )
    except Exception as exc:
        logger.error("yookassa_create_error", error=str(exc))
        await callback.message.edit_text(  # type: ignore[union-attr]
            "⚠️ Ошибка создания платежа. Попробуйте позже."
        )
        await callback.answer()
        return

    # Save deposit
    dep_repo = DepositRepo(session)
    await dep_repo.create(
        user_id=db_user.id,
        amount_rub=amount,
        method="yookassa",
        external_id=payment["payment_id"],
        pay_url=payment["confirmation_url"],
    )
    await session.commit()

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💳 <b>Оплата картой / СБП</b>\n\n"
        f"Сумма: <b>{format_price(amount)}</b>\n\n"
        f"Нажмите кнопку для оплаты.\n"
        f"После оплаты нажмите «Проверить».",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment["confirmation_url"])],
                [InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"check_yookassa:{payment['payment_id']}:{amount}",
                )],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_yookassa:"))
async def cb_check_yookassa(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    yookassa: YooKassaPayment | None,
) -> None:
    if not yookassa:
        await callback.answer("ЮKassa не настроена", show_alert=True)
        return

    parts = callback.data.split(":")  # type: ignore[union-attr]
    payment_id = parts[1]
    amount = int(parts[2])

    try:
        payment = await yookassa.get_payment(payment_id)
    except Exception:
        await callback.answer("Ошибка проверки", show_alert=True)
        return

    if payment["status"] == "succeeded":
        dep_repo = DepositRepo(session)
        dep = await dep_repo.get_by_external_id(payment_id)
        if dep and dep.status == "pending":
            await dep_repo.mark_paid(dep.id)
            user_repo = UserRepo(session)
            new_balance = await user_repo.update_balance(db_user.id, amount)
            tx_repo = TransactionRepo(session)
            await tx_repo.create(
                user_id=db_user.id,
                delta=amount,
                reason=f"Пополнение ЮKassa #{payment_id[:8]}",
            )
            await session.commit()

            await callback.message.edit_text(  # type: ignore[union-attr]
                f"✅ <b>Оплата получена!</b>\n\n"
                f"Зачислено: {format_price(amount)}\n"
                f"Баланс: {format_price(new_balance)}",
                parse_mode="HTML",
            )
        else:
            await callback.answer("✅ Уже зачислено!", show_alert=True)
    elif payment["status"] == "canceled":
        await callback.message.edit_text("❌ Платёж отменён.")  # type: ignore[union-attr]
    else:
        await callback.answer("⏳ Оплата ещё не получена. Подождите.", show_alert=True)

    await callback.answer()
