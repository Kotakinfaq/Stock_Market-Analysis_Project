"""IDX tick sizes (fraksi harga) for the regular market.

Used later so any price level the AI brief mentions is one the market can actually trade at.

VERIFY before relying on this: the table below is the five-band rule as understood when this
was written. Confirm it against the current IDX trading rules (Peraturan II-A) and update
TICK_BANDS if IDX has changed it.
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

# (price at or above, tick size in rupiah), highest band first
TICK_BANDS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal(5000), Decimal(25)),
    (Decimal(2000), Decimal(10)),
    (Decimal(500), Decimal(5)),
    (Decimal(200), Decimal(2)),
    (Decimal(0), Decimal(1)),
)


def tick_size(price: Decimal | float) -> Decimal:
    p = Decimal(str(price))
    if p <= 0:
        raise ValueError(f"Price must be positive: {price}")
    for floor, tick in TICK_BANDS:
        if p >= floor:
            return tick
    raise AssertionError("unreachable")


def round_to_tick(price: Decimal | float) -> Decimal:
    """Round a price to the nearest valid tick for its band."""
    p = Decimal(str(price))
    tick = tick_size(p)
    rounded = (p / tick).quantize(Decimal(1), rounding=ROUND_HALF_UP) * tick
    # Rounding up can cross into a band with a bigger tick (e.g. 4998 -> 5000 is fine,
    # but check the result is valid in its own band).
    new_tick = tick_size(rounded)
    if rounded % new_tick != 0:
        rounded = (rounded / new_tick).quantize(Decimal(1), rounding=ROUND_FLOOR) * new_tick
    return rounded


def is_valid_price(price: Decimal | float) -> bool:
    p = Decimal(str(price))
    return p > 0 and p % tick_size(p) == 0
