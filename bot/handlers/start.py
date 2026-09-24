from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.kb import main_menu_kb

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Здесь вы можете приобрести:\n"
        "• 🤖 Подписки на нейросети (ChatGPT, Claude, Gemini, Perplexity)\n"
        "• 🎵 Мультимедиа сервисы (Spotify, CapCut, Duolingo)\n"
        "• 🎮 Пополнение Steam и игры\n\n"
        "Выберите раздел в меню ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("cancel"))
async def cmd_cancel_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Текущее действие отменено.", reply_markup=main_menu_kb())



from bot.keyboards.kb import help_info_kb, main_menu_kb


@router.message(F.text.in_(["ℹ️ Информация", "ℹ️ Помощь", "ℹ️ Помощь и контакты", "/help", "/info"]))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Информация, поддержка и документы</b>\n\n"
        "🛒 <b>Каталог</b> — официальные подписки на AI и медиа-сервисы\n"
        "🎮 <b>Steam / Игры</b> — пополнение баланса Steam и лицензионные ключи\n"
        "💰 <b>Мой баланс</b> — удобное пополнение через СБП, карты и криптовалюту\n"
        "📜 <b>История</b> — архив ваших покупок и сохранённых ключей\n\n"
        "По всем вопросам обращайтесь в службу поддержки. Ознакомиться с правилами сервиса и офертой вы можете по кнопкам ниже 👇",
        parse_mode="HTML",
        reply_markup=help_info_kb(support_username="V1sionHere"),
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
