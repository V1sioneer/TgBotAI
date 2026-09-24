from __future__ import annotations

import math


def calculate_user_price(partner_price: float, markup_percent: float) -> float:
    """Calculate user price with markup, rounded up to nearest 1 RUB."""
    raw = partner_price * (1 + markup_percent / 100)
    return float(math.ceil(raw))
