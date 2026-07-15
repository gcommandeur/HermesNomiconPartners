from pydantic import BaseModel


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total_count: int
    limit: int
    offset: int
