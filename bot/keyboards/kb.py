from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.services.partner_api import Product
from bot.services.pricing import calculate_user_price
from bot.utils.formatting import format_price


# ── Reply Keyboard (main menu) ──────────────────────────────────────


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 Каталог"),
                KeyboardButton(text="⭐ Звёзды / Premium"),
            ],
            [
                KeyboardButton(text="🎮 Steam / Игры"),
                KeyboardButton(text="💰 Мой баланс"),
            ],
            [
                KeyboardButton(text="📜 История"),
                KeyboardButton(text="ℹ️ Помощь"),
            ],
        ],
        resize_keyboard=True,
    )


# ── Catalog ──────────────────────────────────────────────────────────


def catalog_page_kb(
    products: list[Product],
    page: int,
    total_pages: int,
    markup_percent: float,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for p in products:
        user_price = calculate_user_price(p.price, markup_percent)
        stock_icon = "✅" if p.in_stock else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{stock_icon} {p.name} — {format_price(user_price)}",
                callback_data=f"product:{p.id}",
            )
        ])

    # Pagination
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"catalog_page:{page - 1}")
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop"
        )
    )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(text="➡️", callback_data=f"catalog_page:{page + 1}")
        )
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_card_kb(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Купить 1 шт.",
                    callback_data=f"buy_catalog:{product_id}:1",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📦 Купить N шт.",
                    callback_data=f"buy_catalog_qty:{product_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к каталогу",
                    callback_data="catalog_page:0",
                ),
            ],
        ]
    )


def confirm_purchase_kb(product_id: int, qty: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"confirm_catalog:{product_id}:{qty}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_purchase",
                ),
            ],
        ]
    )


# ── Telegram Stars / Premium ────────────────────────────────────────


def telegram_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Звёзды", callback_data="tg_type:stars"
                ),
                InlineKeyboardButton(
                    text="💎 Premium", callback_data="tg_type:premium"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data="back_main"
                ),
            ],
        ]
    )


def premium_months_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="3 мес.", callback_data="premium_months:3"),
                InlineKeyboardButton(text="6 мес.", callback_data="premium_months:6"),
                InlineKeyboardButton(text="12 мес.", callback_data="premium_months:12"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="tg_type_back"),
            ],
        ]
    )


def confirm_external_kb(action: str, params: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"confirm_ext:{action}:{params}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_purchase",
                ),
            ],
        ]
    )


# ── Steam ────────────────────────────────────────────────────────────


def steam_games_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Пополнение Steam",
                    callback_data="steam_topup",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎮 Игры",
                    callback_data="games_list",
                ),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main"),
            ],
        ]
    )


# ── Balance ──────────────────────────────────────────────────────────


def balance_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Пополнить",
                    callback_data="topup_balance",
                ),
            ],
        ]
    )


# ── History pagination ───────────────────────────────────────────────


def history_page_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"history_page:{page - 1}")
        )
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(text="➡️", callback_data=f"history_page:{page + 1}")
        )
    return InlineKeyboardMarkup(inline_keyboard=[nav] if nav else [])


# ── Generic ──────────────────────────────────────────────────────────


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
        ]
    )
