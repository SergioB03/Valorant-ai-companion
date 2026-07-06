import json
import os
import secrets

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.db import get_analytics_summary, insert_events
from app.limiter import limiter

router = APIRouter(prefix="/analytics", tags=["analytics"])

MAX_PROPS_BYTES = 1024


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    ts: int  # client ms epoch; server-received time is stored separately
    path: str | None = Field(default=None, max_length=128)
    props: dict = Field(default_factory=dict)

    @field_validator("props")
    @classmethod
    def props_must_be_small(cls, v: dict) -> dict:
        if len(json.dumps(v, separators=(",", ":"))) > MAX_PROPS_BYTES:
            raise ValueError(f"props serialized size exceeds {MAX_PROPS_BYTES} bytes")
        return v


class EventBatch(BaseModel):
    visitor_id: str = Field(min_length=8, max_length=64)
    session_id: str = Field(min_length=8, max_length=64)
    events: list[EventIn] = Field(min_length=1, max_length=25)


@router.post("/events", status_code=204)
@limiter.limit("120/minute")
def ingest_events(request: Request, batch: EventBatch):
    insert_events(
        batch.visitor_id,
        batch.session_id,
        [event.model_dump() for event in batch.events],
    )
    return None


@router.get("/summary")
def summary(x_admin_token: str | None = Header(default=None)):
    admin_token = os.getenv("ADMIN_TOKEN", "")
    if not admin_token:
        raise HTTPException(status_code=403, detail="analytics summary disabled")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, admin_token):
        raise HTTPException(status_code=403, detail="invalid admin token")
    return get_analytics_summary()
