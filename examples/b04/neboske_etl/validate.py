"""CSV の 1 行（文字列だけの dict）を、検証済みの Order に変えます。"""
from datetime import datetime, timezone

from .models import CSV_TIMEZONE, VALID_STATUSES, Order, ValidationError


def _to_int(row: dict[str, str], field: str, minimum: int) -> int:
    raw = (row.get(field) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError(field, f"整数ではありません: {raw!r}") from None
    if value < minimum:
        raise ValidationError(field, f"{minimum} 以上でなければなりません: {value}")
    return value


def parse_order(row: dict[str, str]) -> Order:
    """正しければ Order を返し、悪ければ ValidationError を投げます。"""
    status = (row.get("status") or "").strip().lower()  # "SHIPPED" の表記ゆれをそろえる
    if status not in VALID_STATUSES:
        raise ValidationError("status", f"知らない値です: {row.get('status')!r}")
    try:
        local = datetime.strptime((row.get("ordered_at") or "").strip(), "%Y-%m-%d %H:%M:%S")
        ordered_at = local.replace(tzinfo=CSV_TIMEZONE).astimezone(timezone.utc)  # JST を UTC にそろえる
    except ValueError:
        raise ValidationError("ordered_at", f"日時として読めません: {row.get('ordered_at')!r}") from None
    return Order(
        order_id=_to_int(row, "order_id", minimum=1),
        customer_id=_to_int(row, "customer_id", minimum=1),
        ordered_at=ordered_at,
        status=status,
        item_count=_to_int(row, "item_count", minimum=1),
        total_amount=_to_int(row, "total_amount", minimum=0),
    )
