"""
Auction domain: status computation (DRAFT/ACTIVE/CLOSED), winner info, auction→dict.
Pure functions; no I/O.
"""
from datetime import datetime, timezone
from typing import Any

from app.models.auction import Auction


def auction_to_dict(a: Auction) -> dict[str, Any]:
    """Single place for Auction model → API dict. Used by auction and bidding services."""
    return {
        "id": a.id,
        "title": a.title,
        "description": a.description or "",
        "starting_price": a.starting_price,
        "current_price": a.current_price,
        "reserve_price": a.reserve_price,
        "start_time": a.start_time,
        "end_time": a.end_time,
        "status": a.status,
        "highest_bidder_id": a.highest_bidder_id,
        "product_id": str(a.product_id) if a.product_id else None,
        "image_front": a.image_front,
        "image_back": a.image_back,
        "video_url": a.video_url,
        "buy_now_enabled": a.buy_now_enabled or False,
        "buy_now_price": a.buy_now_price,
        "buy_now_url": a.buy_now_url,
    }


def _to_datetime(v: Any) -> datetime | None:
    """
    Normalize to datetime: return datetime as-is, parse string (ISO with Z → +00:00).
    Single place for datetime/string handling; use isinstance only (no hasattr/dead branches).
    Returns None on malformed input to avoid unhandled ValueError.
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None

STATUS_DRAFT = "DRAFT"
STATUS_ACTIVE = "ACTIVE"
STATUS_CLOSED = "CLOSED"

# Message when auction is closed but reserve was not reached (no placeholder: winner_id is in winner_id field). Replace with i18n key in multilingua.
RESERVE_NOT_REACHED_MESSAGE = "Il vincitore non ha raggiunto il prezzo di riserva"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_before(a: datetime, b: datetime) -> bool:
    a_ts = a.timestamp() if a.tzinfo else (a.replace(tzinfo=timezone.utc).timestamp())
    b_ts = b.timestamp() if b.tzinfo else (b.replace(tzinfo=timezone.utc).timestamp())
    return a_ts < b_ts


def compute_status(start_time: datetime, end_time: datetime) -> str:
    n = _now()
    if _is_before(n, start_time):
        return STATUS_DRAFT
    if _is_before(n, end_time):
        return STATUS_ACTIVE
    return STATUS_CLOSED


def with_current_status(auction: dict[str, Any]) -> dict[str, Any]:
    """Return auction dict with status recalculated from start_time/end_time. Uses UNKNOWN if dates are missing/invalid."""
    start = _to_datetime(auction.get("start_time"))
    end = _to_datetime(auction.get("end_time"))
    if start is None or end is None:
        return {**auction, "status": "UNKNOWN"}
    status = compute_status(start, end)
    return {**auction, "status": status}


def with_winner_info(auction: dict[str, Any]) -> dict[str, Any]:
    """When CLOSED, add winner_id and optional reserve_not_reached_message."""
    out = dict(auction)
    if out.get("status") != STATUS_CLOSED:
        return out
    if out.get("highest_bidder_id") is not None:
        out["winner_id"] = out["highest_bidder_id"]
        reserve = out.get("reserve_price")
        if reserve is not None and float(out.get("current_price", 0)) < float(reserve):
            out["reserve_not_reached_message"] = RESERVE_NOT_REACHED_MESSAGE
    return out
