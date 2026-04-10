from app.api.auctions import router as auctions_router
from app.api.bids import router as bids_router
from app.api.me import router as me_router
from app.api.products import router as products_router

__all__ = ["auctions_router", "bids_router", "me_router", "products_router"]
