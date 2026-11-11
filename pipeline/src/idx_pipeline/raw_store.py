"""Keep every raw response exactly as received, so history can be rebuilt after any vendor change.

Phase 0 writes to a local folder. Later this can point at Cloudflare R2 or Supabase Storage
without changing the callers.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, source: str, kind: str, key: str, payload: Any, fetched_at: datetime) -> str:
        stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
        path = self.root / source / kind / fetched_at.strftime("%Y-%m-%d") / f"{key}_{stamp}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return str(path.relative_to(self.root))
