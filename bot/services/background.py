from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from bot.db.models import OrderStatus
from bot.db.repo import OrderRepo, PartnerDepositRepo, TransactionRepo, UserRepo
from bot.services.partner_api import PartnerAPIClient, PartnerAPIError

logger = structlog.get_logger()


async def poll_external_orders(
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    api: PartnerAPIClient,
    admin_ids: list[int],
    interval: float = 15.0,
    max_age_minutes: float = 30.0,
) -> None:
    """Background task: poll external orders (Fragment/Steam/Games) for status updates."""
    logger.info("background_task_started", task="poll_external_orders")

    while True:
        try:
            await asyncio.sleep(interval)

            async with session_factory() as session:
                order_repo = OrderRepo(session)
                orders = await order_repo.get_processing_external()

                if not orders:
                    continue

                logger.debug("polling_external_orders", count=len(orders))

                for order in orders:
                    if order.partner_order_id is None:
                        continue

                    try:
                        status_resp = await api.get_external_status(
                            order.partner_order_id
                        )
                    except PartnerAPIError as exc:
                        logger.warning(
                            "poll_status_error",
                            order_id=order.id,
                            partner_order_id=order.partner_order_id,
                            error=str(exc),
                        )
                        continue

                    new_status = status_resp.status.lower()

                    if new_status in ("success", "completed"):
                        await order_repo.update_status(
                            order.id,
                            OrderStatus.SUCCESS,
                            delivered_data="Заказ выполнен",
                        )
                        await session.commit()

                        # Notify user
                        try:
                            await bot.send_message(
                                order.user_id,
                                f"✅ <b>Заказ #{order.id} выполнен!</b>\n\n"
                                f"Ваш заказ успешно обработан.",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                        logger.info(
                            "order_completed",
                            order_id=order.id,
                            partner_order_id=order.partner_order_id,
                        )

                    elif new_status == "failed":
                        # Refund user
                        user_repo = UserRepo(session)
                        tx_repo = TransactionRepo(session)

                        await user_repo.update_balance(
                            order.user_id, order.user_price
                        )
                        await tx_repo.create(
                            user_id=order.user_id,
                            delta=order.user_price,
                            reason="Возврат: заказ не выполнен",
                            order_id=order.id,
                        )
                        await order_repo.update_status(
                            order.id, OrderStatus.FAILED
                        )
                        await session.commit()

                        # Notify user
                        try:
                            await bot.send_message(
                                order.user_id,
                                f"❌ <b>Заказ #{order.id} не выполнен</b>\n\n"
                                f"Средства возвращены на ваш баланс: "
                                f"{order.user_price:.0f} ₽",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                        logger.info(
                            "order_failed_refunded",
                            order_id=order.id,
                            user_id=order.user_id,
                            refund=order.user_price,
                        )

                    elif new_status == "uncertain":
                        await order_repo.update_status(
                            order.id, OrderStatus.UNCERTAIN
                        )
                        await session.commit()

                        # Notify user
                        try:
                            await bot.send_message(
                                order.user_id,
                                f"⚠️ <b>Заказ #{order.id}</b>\n\n"
                                f"Статус заказа уточняется. "
                                f"Средства заморожены, ожидайте решения.",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                        # Alert admins
                        for aid in admin_ids:
                            try:
                                await bot.send_message(
                                    aid,
                                    f"⚠️ <b>UNCERTAIN ORDER #{order.id}</b>\n"
                                    f"User: {order.user_id}\n"
                                    f"Partner order: {order.partner_order_id}\n"
                                    f"Amount: {order.user_price:.0f} ₽\n"
                                    f"Требует ручного разбора!",
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass

                        logger.warning(
                            "order_uncertain",
                            order_id=order.id,
                            partner_order_id=order.partner_order_id,
                        )

                    # else: still processing, do nothing

        except asyncio.CancelledError:
            logger.info("poll_external_orders_cancelled")
            break
        except Exception as exc:
            logger.error("poll_external_orders_error", error=str(exc))
            await asyncio.sleep(30)


async def poll_partner_deposits(
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    api: PartnerAPIClient,
    admin_ids: list[int],
    interval: float = 20.0,
) -> None:
    """Background task: poll pending partner deposits for payment confirmation."""
    logger.info("background_task_started", task="poll_partner_deposits")

    while True:
        try:
            await asyncio.sleep(interval)

            async with session_factory() as session:
                dep_repo = PartnerDepositRepo(session)
                pending = await dep_repo.get_pending()

                for dep in pending:
                    try:
                        result = await api.get_deposit(dep.deposit_id_partner)
                    except PartnerAPIError:
                        continue

                    if result.status == "paid":
                        await dep_repo.update_status(
                            dep.deposit_id_partner, "paid"
                        )
                        await session.commit()

                        # Notify admins
                        for aid in admin_ids:
                            try:
                                await bot.send_message(
                                    aid,
                                    f"✅ <b>Депозит #{dep.deposit_id_partner} оплачен!</b>\n"
                                    f"Сумма: {dep.amount_rub:.0f} ₽\n"
                                    f"Баланс пополнен.",
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass

                        logger.info(
                            "deposit_paid",
                            deposit_id=dep.deposit_id_partner,
                            amount_rub=dep.amount_rub,
                        )

        except asyncio.CancelledError:
            logger.info("poll_partner_deposits_cancelled")
            break
        except Exception as exc:
            logger.error("poll_partner_deposits_error", error=str(exc))
            await asyncio.sleep(30)
