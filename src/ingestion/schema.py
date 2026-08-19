from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedReview:
    review_id: str
    platform: str
    date: str
    rating: int
    title: str
    body: str
    app_version: str
    thumbs_up: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedReview:
        return cls(
            review_id=str(data["review_id"]),
            platform=str(data["platform"]),
            date=str(data["date"]),
            rating=int(data["rating"]),
            title=str(data.get("title", "")),
            body=str(data["body"]),
            app_version=str(data.get("app_version", "")),
            thumbs_up=int(data.get("thumbs_up", 0)),
        )
