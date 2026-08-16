import base64
import binascii
import io
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from infrai_storage import Infrai, InfraiError


BUCKET = "player-generated-assets"
MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_EDGE = 1600


class ModerationState(StrEnum):
    QUEUED = "queued"
    APPROVED = "approved"


class AssetUpload(BaseModel):
    asset_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,80}$")
    player_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,80}$")
    live_event_id: str | None = Field(
        default=None, pattern=r"^[a-zA-Z0-9_-]{3,80}$"
    )
    content_type: str
    data_base64: str
    send_to_moderation: bool = True


class StoredAsset(BaseModel):
    asset_id: str
    player_id: str
    live_event_id: str | None
    object_key: str
    width: int
    height: int
    content_type: str
    moderation_state: ModerationState
    moderation_queue: str | None


@dataclass
class InfraiAssetStore:
    infrai: Infrai
    http: httpx.AsyncClient

    async def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str,
        idempotency_key: str,
    ) -> None:
        signed = await self.infrai.storage.object.presign(
            BUCKET,
            key,
            content_type=content_type,
            max_bytes=len(content),
            idempotency_key=idempotency_key,
        )
        response = await self.http.request(
            method="PUT",
            url=signed.url,
            headers={"Content-Type": content_type},
            content=content,
        )
        response.raise_for_status()


def resize_for_game(source: bytes) -> tuple[bytes, int, int]:
    try:
        with Image.open(io.BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue(), image.width, image.height
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Upload must contain a readable image") from exc


async def process_upload(upload: AssetUpload, store: Any) -> StoredAsset:
    if upload.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("content_type must be image/jpeg, image/png, or image/webp")
    try:
        source = base64.b64decode(upload.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("data_base64 must be valid base64") from exc
    if not source or len(source) > MAX_SOURCE_BYTES:
        raise ValueError("Image must be between 1 byte and 12 MiB")

    resized, width, height = resize_for_game(source)
    event_segment = upload.live_event_id or "profile"
    key = f"players/{upload.player_id}/{event_segment}/{upload.asset_id}.jpg"
    await store.put(
        key=key,
        content=resized,
        content_type="image/jpeg",
        idempotency_key=f"asset-{upload.asset_id}",
    )
    queued = upload.send_to_moderation
    return StoredAsset(
        asset_id=upload.asset_id,
        player_id=upload.player_id,
        live_event_id=upload.live_event_id,
        object_key=key,
        width=width,
        height=height,
        content_type="image/jpeg",
        moderation_state=(
            ModerationState.QUEUED if queued else ModerationState.APPROVED
        ),
        moderation_queue="player-image-review" if queued else None,
    )


def get_store(request: Request) -> Any:
    return request.app.state.asset_store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")
    async with httpx.AsyncClient(timeout=30) as client:
        infrai = Infrai(api_key, client)
        await infrai.storage.bucket.create(name=BUCKET)
        app.state.asset_store = InfraiAssetStore(infrai, client)
        yield


app = FastAPI(title="Game media upload service", lifespan=lifespan)


@app.post("/assets", response_model=StoredAsset, status_code=201)
async def upload_asset(
    upload: AssetUpload, store: Any = Depends(get_store)
) -> StoredAsset:
    try:
        return await process_upload(upload, store)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
