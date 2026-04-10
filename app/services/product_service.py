"""
Product business logic: search, get by id, create. Pagination on list.
Accepts Decimal for price from API; converts to float at repository boundary (DB uses float).
"""
from decimal import Decimal
from typing import Any, Optional, Union
from uuid import UUID

from app.core.cache import get_cached, loading_lock, set_cached
from app.repositories.product_repository import ProductCreateDTO, ProductRepository


class ProductService:
    def __init__(self, product_repo: ProductRepository) -> None:
        self._product_repo = product_repo

    async def search_products(
        self,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Returns (items, total_count) for pagination."""
        products, total = await self._product_repo.search(q=q, limit=limit, offset=offset)
        items = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "price": p.price,
                "image_front": p.image_front,
                "image_back": p.image_back,
                "condition": p.condition,
            }
            for p in products
        ]
        return items, total

    async def get_product_by_id(self, id: int) -> Optional[dict[str, Any]]:
        cached = await get_cached("product", id)
        if cached is not None:
            return cached
        async with loading_lock("product", id):
            cached = await get_cached("product", id)
            if cached is not None:
                return cached
            product = await self._product_repo.find_by_id(id)
            if not product:
                return None
            d = {
                "id": product.id,
                "name": product.name,
                "description": product.description or "",
                "price": product.price,
                "image_front": product.image_front,
                "image_back": product.image_back,
                "condition": product.condition,
            }
            await set_cached("product", id, d)
            return d

    async def create_product(
        self,
        name: str,
        created_by_user_id: UUID,
        description: str = "",
        price: Union[Decimal, float] = 0,
        image_front: str = "",
        image_back: str = "",
        condition: str = "",
    ) -> dict[str, Any]:
        _price = float(price) if isinstance(price, Decimal) else price
        product = await self._product_repo.create(
            ProductCreateDTO(
                name=name,
                description=description,
                price=_price,
                image_front=image_front,
                image_back=image_back,
                condition=condition,
                created_by_user_id=created_by_user_id,
            )
        )
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description or "",
            "price": product.price,
            "image_front": product.image_front,
            "image_back": product.image_back,
            "condition": product.condition,
        }
