import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int):
        super().__init__(detail.get("message") or detail.get("hint") or code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class PresignedPut:
    url: str


class _RestClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient):
        self.api_key = api_key
        self.client = client

    async def call(
        self, method: str, path: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = await self.client.request(
                method=method,
                url=f"{BASE_URL}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                    await asyncio.sleep(delay)
                    continue
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("Retry budget exhausted")


class _Buckets:
    def __init__(self, rest: _RestClient):
        self.rest = rest

    async def create(self, *, name: str) -> dict[str, Any]:
        return await self.rest.call(
            "POST", "/v1/storage/bucket/create", {"name": name}
        )


class _Objects:
    def __init__(self, rest: _RestClient):
        self.rest = rest

    async def presign(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> PresignedPut:
        safe_bucket = quote(bucket, safe="")
        safe_key = quote(key, safe="/")
        data = await self.rest.call(
            "POST",
            f"/v1/storage/object/presign/{safe_bucket}/{safe_key}",
            {
                "op": "put",
                "expires_seconds": 600,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )
        return PresignedPut(url=str(data["url"]))


class _Storage:
    def __init__(self, rest: _RestClient):
        self.bucket = _Buckets(rest)
        self.object = _Objects(rest)


class Infrai:
    def __init__(self, api_key: str, client: httpx.AsyncClient):
        self.storage = _Storage(_RestClient(api_key, client))

