from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.keyboards.kb import main_menu_kb

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Здесь вы можете приобрести:\n"
        "• Подписки и ключи из каталога\n"
        "• ⭐ Звёзды и 💎 Premium Telegram\n"
        "• 🎮 Пополнение Steam и игры\n\n"
        "Выберите раздел в меню ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>ℹ️ Помощь</b>\n\n"
        "🛒 <b>Каталог</b> — цифровые товары и ключи\n"
        "⭐ <b>Звёзды / Premium</b> — покупка через Fragment\n"
        "🎮 <b>Steam / Игры</b> — пополнение и игры\n"
        "💰 <b>Мой баланс</b> — проверка и пополнение\n"
        "📜 <b>История</b> — ваши покупки\n\n"
        "По вопросам пишите администратору.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Выберите раздел:",
        reply_markup=None,
    )
    await callback.message.answer(  # type: ignore[union-attr]
        "Главное меню 👇",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "cancel_purchase")
async def cb_cancel(callback: CallbackQuery) -> None:
    await callback.message.edit_text("❌ Покупка отменена.")  # type: ignore[union-attr]
    await callback.answer()
