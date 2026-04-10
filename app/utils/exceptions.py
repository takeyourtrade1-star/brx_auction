"""
Centralized application exceptions. Never expose stack trace or SQL to client.
Responses are standard JSON: {"detail": "...", "code": "..."}.
"""
from typing import Any, Optional


class AppError(Exception):
    """Base app error with code and HTTP status."""

    def __init__(
        self,
        message: str,
        code: str = "ERROR",
        status_code: int = 400,
        detail: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail or {}


# Auction
class AuctionNotFoundError(AppError):
    def __init__(self, message: str = "Auction not found."):
        super().__init__(message, code="AUCTION_NOT_FOUND", status_code=404)


class AuctionNotActiveError(AppError):
    def __init__(self, message: str = "Auction is not active or has ended."):
        super().__init__(message, code="AUCTION_NOT_ACTIVE", status_code=400)


class InvalidAuctionDataError(AppError):
    def __init__(self, message: str = "Invalid auction data."):
        super().__init__(message, code="INVALID_AUCTION_DATA", status_code=400)


# Bid
class BidTooLowError(AppError):
    def __init__(self, message: str = "Bid amount is below the minimum required."):
        super().__init__(message, code="BID_TOO_LOW", status_code=400)


class BidAboveMaxError(AppError):
    def __init__(self, message: str = "In a single bid, amount cannot be greater than maxAmount."):
        super().__init__(message, code="BID_ABOVE_MAX", status_code=400)


# Product
class ProductNotFoundError(AppError):
    def __init__(self, message: str = "Product not found."):
        super().__init__(message, code="PRODUCT_NOT_FOUND", status_code=404)


# P.IVA (venditori con partita IVA)
class PivaRequiredError(AppError):
    def __init__(self, message: str = "This feature is only available for sellers with VAT number (partita IVA)."):
        super().__init__(message, code="PIVA_REQUIRED", status_code=403)


# Generic
class InvalidIdError(AppError):
    def __init__(self, message: str = "Invalid id."):
        super().__init__(message, code="INVALID_ID", status_code=400)


class ValidationError(AppError):
    def __init__(self, message: str, detail: Optional[dict[str, Any]] = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400, detail=detail)
