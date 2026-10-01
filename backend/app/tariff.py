# Biểu giá bậc thang điện sinh hoạt EVN (VNĐ/kWh, giá trước VAT).
# Cập nhật lại các mốc/giá này khi Bộ Công Thương ban hành biểu giá mới.
# Mỗi phần tử: (giới hạn kWh của bậc, giá VNĐ/kWh). Bậc cuối limit=None ("từ ... trở lên").
TIERS: list[tuple[int | None, int]] = [
    (50, 1893),
    (100, 1956),
    (200, 2271),
    (300, 2860),
    (400, 3197),
    (None, 3302),
]

VAT_RATE = 0.08


def estimate_cost(kwh: float) -> float:
    """Ước tính tiền điện (đã gồm VAT) cho lượng điện tiêu thụ trong 1 tháng."""
    if kwh <= 0:
        return 0.0

    remaining = kwh
    prev_limit = 0
    total = 0.0
    for limit, price in TIERS:
        tier_capacity = (limit - prev_limit) if limit is not None else remaining
        tier_kwh = min(remaining, tier_capacity)
        if tier_kwh > 0:
            total += tier_kwh * price
            remaining -= tier_kwh
        if limit is not None:
            prev_limit = limit
        if remaining <= 0:
            break

    return total * (1 + VAT_RATE)
