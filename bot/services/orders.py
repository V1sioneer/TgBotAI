from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import OrderStatus, OrderType
from bot.db.repo import OrderRepo, TransactionRepo, UserRepo
from bot.services.partner_api import (
    ExternalOrder,
    OrderResult,
    PartnerAPIClient,
    PartnerAPIError,
)
from bot.services.pricing import calculate_user_price

logger = structlog.get_logger()


class InsufficientUserBalance(Exception):
    pass


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        api: PartnerAPIClient,
        markup_percent: float,
    ) -> None:
        self.session = session
        self.api = api
        self.markup = markup_percent
        self.users = UserRepo(session)
        self.orders = OrderRepo(session)
        self.txns = TransactionRepo(session)

    async def buy_catalog_product(
        self,
        user_id: int,
        product_id: int,
        qty: int = 1,
    ) -> tuple[OrderResult, float]:
        """
        Buy a catalog product.
        Returns (OrderResult from API, user_price).
        Raises InsufficientUserBalance, PartnerAPIError.
        """
        product = await self.api.get_product(product_id)
        partner_price = product.price * qty
        user_price = calculate_user_price(product.price, self.markup) * qty

        # Check user balance
        user = await self.users.get(user_id)
        if user is None or user.balance_rub < user_price:
            raise InsufficientUserBalance(
                f"Нужно {user_price:.0f} ₽, на балансе {user.balance_rub:.0f} ₽"
                if user
                else "Пользователь не найден"
            )

        # Create local order (pending) — idempotency anchor
        local_order = await self.orders.create(
            user_id=user_id,
            order_type=OrderType.CATALOG,
            partner_price=partner_price,
            user_price=user_price,
            product_id=product_id,
            qty=qty,
            payload={"product_id": product_id, "qty": qty},
            status=OrderStatus.PENDING,
        )

        # Debit user balance
        await self.users.update_balance(user_id, -user_price)
        await self.txns.create(
            user_id=user_id,
            delta=-user_price,
            reason=f"Покупка: {product.name} x{qty}",
            order_id=local_order.id,
        )

        try:
            result = await self.api.create_order(product_id, qty)
        except PartnerAPIError as exc:
            # Rollback: refund user
            await self.users.update_balance(user_id, user_price)
            await self.txns.create(
                user_id=user_id,
                delta=user_price,
                reason=f"Возврат: ошибка API ({exc.code})",
                order_id=local_order.id,
            )
            await self.orders.update_status(
                local_order.id,
                OrderStatus.FAILED,
                error_code=exc.code,
            )
            await self.session.commit()
            raise

        # Update order with success
        await self.orders.update_status(
            local_order.id,
            OrderStatus.SUCCESS,
            partner_order_id=result.order_id,
            delivered_data=result.delivered_data,
        )
        await self.session.commit()

        return result, user_price

    async def buy_external(
        self,
        user_id: int,
        order_type: OrderType,
        user_price: float,
        partner_price: float,
        api_call,
        product_name: str,
        product_id: int | None = None,
        variation_id: int | None = None,
        payload: dict | None = None,
    ) -> tuple[ExternalOrder, int]:
        """
        Buy an external product (Steam/Game).
        api_call should be an awaitable that calls the partner API.
        Returns (ExternalOrder, local_order_id).
        """
        # Check user balance
        user = await self.users.get(user_id)
        if user is None or user.balance_rub < user_price:
            raise InsufficientUserBalance(
                f"Нужно {user_price:.0f} ₽, на балансе {user.balance_rub:.0f} ₽"
                if user
                else "Пользователь не найден"
            )

        # Create local order
        local_order = await self.orders.create(
            user_id=user_id,
            order_type=order_type,
            partner_price=partner_price,
            user_price=user_price,
            product_id=product_id,
            variation_id=variation_id,
            payload=payload,
            status=OrderStatus.PENDING,
        )

        # Debit user
        await self.users.update_balance(user_id, -user_price)
        await self.txns.create(
            user_id=user_id,
            delta=-user_price,
            reason=f"Покупка: {product_name}",
            order_id=local_order.id,
        )

        try:
            result: ExternalOrder = await api_call
        except PartnerAPIError as exc:
            # Rollback
            await self.users.update_balance(user_id, user_price)
            await self.txns.create(
                user_id=user_id,
                delta=user_price,
                reason=f"Возврат: ошибка API ({exc.code})",
                order_id=local_order.id,
            )
            await self.orders.update_status(
                local_order.id,
                OrderStatus.FAILED,
                error_code=exc.code,
            )
            await self.session.commit()
            raise

        # Mark as processing
        await self.orders.update_status(
            local_order.id,
            OrderStatus.PROCESSING,
            partner_order_id=result.order_id,
        )
        await self.session.commit()

        return result, local_order.id

    async def refund_order(self, order_id: int) -> None:
        """Refund user for a failed external order."""
        order = await self.orders.get(order_id)
        if order is None:
            return
        await self.users.update_balance(order.user_id, order.user_price)
        await self.txns.create(
            user_id=order.user_id,
            delta=order.user_price,
            reason="Возврат: заказ не выполнен",
            order_id=order_id,
        )
        await self.orders.update_status(order_id, OrderStatus.FAILED)
        await self.session.commit()
