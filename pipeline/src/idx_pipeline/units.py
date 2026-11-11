"""Volume units. IDX trades in lots of 100 shares; sources differ in which unit they report.

Everything stored in the database is in shares. Each provider declares its unit, and the
cross-source check flags pairs whose volumes differ by a factor of about 100.
"""

from __future__ import annotations

from enum import StrEnum

SHARES_PER_LOT = 100


class VolumeUnit(StrEnum):
    SHARES = "shares"
    LOTS = "lots"


def to_shares(volume: float | None, unit: VolumeUnit) -> int | None:
    if volume is None:
        return None
    volume = round(volume)
    if volume < 0:
        raise ValueError(f"Negative volume: {volume}")
    return volume * SHARES_PER_LOT if unit is VolumeUnit.LOTS else volume


def looks_like_lot_mismatch(volume_a: int | None, volume_b: int | None, tolerance: float = 0.05) -> bool:
    """True when one volume is about 100x the other, which usually means lots were stored as shares."""
    if not volume_a or not volume_b:
        return False
    ratio = max(volume_a, volume_b) / min(volume_a, volume_b)
    return abs(ratio - SHARES_PER_LOT) / SHARES_PER_LOT <= tolerance
