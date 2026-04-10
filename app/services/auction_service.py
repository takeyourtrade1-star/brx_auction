"""
Auction business logic: create, list, get by id. Validates product exists when product_id given.
Accepts Decimal for monetary fields from API; converts to float at repository boundary (DB uses float).
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from app.models.auction import Auction
from app.core.cache import get_cached, invalidate_cached, loading_lock, set_cached
from app.repositories.auction_repository import AuctionRepository
from app.repositories.product_repository import ProductRepository
from app.services.auction_domain import (
    _to_datetime,
    auction_to_dict,
    compute_status,
    STATUS_ACTIVE,
    STATUS_CLOSED,
    STATUS_DRAFT,
    with_current_status,
    with_winner_info,
)
from app.utils.exceptions import (
    AuctionNotFoundError,
    AuctionNotActiveError,
    InvalidAuctionDataError,
    InvalidIdError,
    PivaRequiredError,
    ProductNotFoundError,
    ValidationError,
)


class AuctionService:
    """
    Auction CRUD and list. When product_repo is provided, create_auction validates product_id
    (exists and positive). When product_repo is None, product_id is not validated—caller must
    ensure validity or omit product_id.
    """

    def __init__(
        self,
        auction_repo: AuctionRepository,
        product_repo: Optional[ProductRepository] = None,
    ) -> None:
        self._auction_repo = auction_repo
        self._product_repo = product_repo

    def _check_piva_only_fields(self, data: dict[str, Any], has_piva: bool) -> None:
        """Raise PivaRequiredError if non-P.IVA user sends video or buy_now fields."""
        if has_piva:
            return
        if data.get("video_url") or data.get("buy_now_enabled") or data.get("buy_now_url") or data.get("buy_now_price") is not None:
            raise PivaRequiredError()

    async def create_auction(self, data: dict[str, Any]) -> dict[str, Any]:
        has_piva = bool(data.get("has_piva", False))
        self._check_piva_only_fields(data, has_piva)

        title = data.get("title")
        starting_price = data.get("starting_price")
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        if not title or starting_price is None or not start_time or not end_time:
            raise InvalidAuctionDataError("Missing required fields: title, starting_price, start_time, end_time.")
        product_id = data.get("product_id")
        product_inline = data.get("product")
        if product_id is not None and product_inline is not None:
            raise InvalidAuctionDataError("Provide either product_id (existing product) or product (inline), not both.")
        if product_id is None and product_inline is None:
            raise InvalidAuctionDataError("Provide either product_id (existing product) or product (inline product data).")
        if self._product_repo is None:
            raise InvalidAuctionDataError("Product repository not available for product validation/creation.")

        image_front: Optional[str] = None
        image_back: Optional[str] = None
        product_price_for_buy_now: Optional[float] = None

        if product_id is not None:
            try:
                pid = int(product_id) if isinstance(product_id, (int, str)) else 0
            except (ValueError, TypeError):
                raise InvalidIdError(f"product_id must be a valid integer, got: {product_id!r}.")
            if pid <= 0:
                raise InvalidIdError("product_id must be a positive integer.")
            existing = await self._product_repo.find_by_id(pid)
            if existing is None:
                raise ProductNotFoundError(f"Product {product_id} not found.")
            resolved_product_id = str(product_id)
            # Auction images are required and must match the product
            image_front = data["image_front"]
            image_back = data["image_back"]
            if image_front != existing.image_front or image_back != existing.image_back:
                raise InvalidAuctionDataError(
                    "image_front and image_back must match the product's front and back images."
                )
            product_price_for_buy_now = float(existing.price)
        else:
            # Create product inline (price from auction, so product price = 0); images required at auction level
            p = product_inline
            new_product = await self._product_repo.create(
                name=p["name"],
                description=p.get("description", ""),
                price=0.0,
                image_front=p["image_front"],
                image_back=p["image_back"],
                condition=p.get("condition", ""),
                created_by_user_id=data["created_by_user_id"],
            )
            resolved_product_id = str(new_product.id)
            image_front = data["image_front"]
            image_back = data["image_back"]
            product_price_for_buy_now = 0.0

        start = _to_datetime(start_time)
        end = _to_datetime(end_time)
        if start is None or end is None:
            detail = {}
            if start is None and start_time is not None:
                detail["start_time"] = "Must be datetime or ISO 8601 string."
            if end is None and end_time is not None:
                detail["end_time"] = "Must be datetime or ISO 8601 string."
            raise ValidationError(
                "start_time and end_time must be datetime or ISO format string.",
                detail=detail if detail else None,
            )
        if end <= start:
            raise InvalidAuctionDataError("endTime must be after startTime.")
        _start = float(starting_price) if isinstance(starting_price, Decimal) else starting_price
        if _start < 0:
            raise InvalidAuctionDataError("startingPrice must be non-negative.")
        reserve_price = data.get("reserve_price")
        _reserve: Optional[float] = None
        if reserve_price is not None:
            _reserve = float(reserve_price) if isinstance(reserve_price, Decimal) else reserve_price
            if _reserve < 0:
                raise InvalidAuctionDataError("reservePrice must be non-negative.")
            if _reserve < _start:
                raise InvalidAuctionDataError("reservePrice must be >= startingPrice.")

        buy_now_enabled = has_piva and bool(data.get("buy_now_enabled", False))
        buy_now_url = data.get("buy_now_url") if has_piva else None
        buy_now_price = data.get("buy_now_price")
        if buy_now_enabled and not buy_now_url:
            raise InvalidAuctionDataError("buy_now_url is required when buy_now_enabled is true.")
        if buy_now_price is not None:
            buy_now_price = float(buy_now_price) if isinstance(buy_now_price, Decimal) else buy_now_price
        elif buy_now_enabled and product_price_for_buy_now is not None:
            buy_now_price = product_price_for_buy_now
        video_url = data.get("video_url") if has_piva else None

        now = datetime.now(timezone.utc)
        status = STATUS_DRAFT if now < start else (STATUS_ACTIVE if now < end else STATUS_CLOSED)
        create_data = {
            "title": title,
            "description": data.get("description", ""),
            "starting_price": _start,
            "current_price": _start,
            "reserve_price": _reserve,
            "start_time": start,
            "end_time": end,
            "status": status,
            "highest_bidder_id": None,
            "created_by_user_id": data.get("created_by_user_id"),
            "product_id": resolved_product_id,
            "image_front": image_front,
            "image_back": image_back,
            "video_url": video_url,
            "buy_now_enabled": buy_now_enabled,
            "buy_now_price": buy_now_price,
            "buy_now_url": buy_now_url,
        }
        auction = await self._auction_repo.create(create_data)
        d = auction_to_dict(auction)
        return with_winner_info(with_current_status(d))

    async def list_auctions(
        self,
        q: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Returns (items, total_count) for pagination. status filters by auction status (e.g. ACTIVE)."""
        auctions, total = await self._auction_repo.find_all(
            q=q, status=status, limit=limit, offset=offset
        )
        items = [with_winner_info(with_current_status(auction_to_dict(a))) for a in auctions]
        return items, total

    async def get_auction_by_id(self, id: int) -> dict[str, Any]:
        # Optional cache to reduce DB load on hot reads; single-flight load to avoid thundering herd.
        cached = await get_cached("auction", id)
        if cached is not None:
            return cached
        async with loading_lock("auction", id):
            cached = await get_cached("auction", id)
            if cached is not None:
                return cached
            auction = await self._auction_repo.find_by_id(id)
            if not auction:
                raise AuctionNotFoundError()
            d = with_winner_info(with_current_status(auction_to_dict(auction)))
            await set_cached("auction", id, d)
            return d

    async def update_auction_partial(
        self,
        auction_id: int,
        user_id: Any,
        update_data: dict[str, Any],
        has_piva: bool,
    ) -> dict[str, Any]:
        """Update auction (video_url, buy_now_*) only when ACTIVE and owned by user. P.IVA required for video/buy_now."""
        auction = await self._auction_repo.find_by_id(auction_id)
        if not auction:
            raise AuctionNotFoundError()
        if str(auction.created_by_user_id) != str(user_id):
            raise AuctionNotFoundError()
        # Only allow updates while auction is ACTIVE (during the auction)
        current_status = compute_status(auction.start_time, auction.end_time)
        if current_status != STATUS_ACTIVE:
            raise AuctionNotActiveError("Can only update buy-it-now or video while the auction is ACTIVE.")
        if update_data.get("video_url") is not None or update_data.get("buy_now_enabled") is not None or update_data.get("buy_now_url") is not None or update_data.get("buy_now_price") is not None:
            if not has_piva:
                raise PivaRequiredError()
        if "video_url" in update_data and update_data["video_url"] is not None:
            auction.video_url = update_data["video_url"]
        if "buy_now_enabled" in update_data and update_data["buy_now_enabled"] is not None:
            auction.buy_now_enabled = bool(update_data["buy_now_enabled"])
        if "buy_now_url" in update_data:
            auction.buy_now_url = update_data["buy_now_url"]
        if "buy_now_price" in update_data and update_data["buy_now_price"] is not None:
            auction.buy_now_price = float(update_data["buy_now_price"])
        if auction.buy_now_enabled and not auction.buy_now_url:
            raise InvalidAuctionDataError("buy_now_url is required when buy_now_enabled is true.")
        await self._auction_repo.update(auction)
        await invalidate_cached("auction", auction_id)
        d = auction_to_dict(auction)
        return with_winner_info(with_current_status(d))
