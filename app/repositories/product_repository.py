"""
Product repository: async CRUD and search. Uses AsyncSession.
"""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.product import Product


class ProductCreateDTO(BaseModel):
    """DTO for creating a product. Pydantic validates field types."""

    model_config = ConfigDict(validate_assignment=True)

    name: str
    created_by_user_id: UUID
    description: str = ""
    price: float = 0.0
    image_front: str = ""
    image_back: str = ""
    condition: str = ""


class ProductRepository:
    """
    Repository for Product entity: create, lookup, and search.

    Uses Pydantic DTOs for create payloads to keep signatures stable and typed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, dto: ProductCreateDTO) -> Product:
        """
        Persist a new product from a validated DTO.

        Args:
            dto: Required name and owner; optional description, price, images, condition.

        Returns:
            The flushed and refreshed Product row.
        """
        product = Product(
            name=dto.name,
            description=dto.description,
            price=dto.price,
            image_front=dto.image_front,
            image_back=dto.image_back,
            condition=dto.condition,
            created_by_user_id=dto.created_by_user_id,
        )
        self._session.add(product)
        await self._session.flush()
        await self._session.refresh(product)
        return product

    async def find_by_id(self, id: int) -> Optional[Product]:
        """Return the product with the given primary key, or None."""
        result = await self._session.execute(select(Product).where(Product.id == id))
        return result.scalar_one_or_none()

    async def search(
        self,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Product], int]:
        """Search products; returns (items, total_count). Single query with COUNT(*) OVER() to avoid two round-trips."""
        max_offset = get_settings().MAX_PAGINATION_OFFSET
        offset = min(offset, max_offset)

        term = f"%{q.strip().lower()}%" if q and q.strip() else None
        total_expr = func.count(Product.id).over().label("_total")
        stmt = select(Product, total_expr)
        if term:
            stmt = stmt.where(
                or_(Product.name.ilike(term), Product.description.ilike(term))
            )
        stmt = stmt.order_by(Product.id).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        rows = result.all()
        total = int(rows[0][1]) if rows else 0
        products = [row[0] for row in rows]
        return products, total
