"""IDX ticker codes. The canonical form is the 4-character code without a suffix (BBCA, not BBCA.JK)."""

from __future__ import annotations

import re

_CODE = re.compile(r"^[A-Z0-9]{4}$")


def normalize(symbol: str) -> str:
    """Turn 'bbca.jk', 'BBCA.JK' or ' BBCA ' into 'BBCA'. Raises ValueError for anything else."""
    code = symbol.strip().upper()
    code = code.removesuffix(".JK")
    if not _CODE.match(code):
        raise ValueError(f"Not an IDX ticker code: {symbol!r}")
    return code


def to_yahoo(ticker: str) -> str:
    return f"{normalize(ticker)}.JK"


def to_eodhd(ticker: str) -> str:
    return f"{normalize(ticker)}.JK"
