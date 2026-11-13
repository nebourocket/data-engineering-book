"""注文 1 件を表す型と、検証の失敗を表す例外。"""
from dataclasses import dataclass
from datetime import datetime

VALID_STATUSES = frozenset({"placed", "shipped", "delivered", "cancelled"})


class ValidationError(ValueError):
    """1 行の検証の失敗。どの項目が、なぜ悪いかを持ちます。"""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Order:
    order_id: int
    customer_id: int
    ordered_at: datetime
    status: str
    item_count: int
    total_amount: int
