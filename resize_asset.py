import argparse
import asyncio
import base64
from pathlib import Path

import httpx

from game_media_service import BUCKET, InfraiAssetStore, AssetUpload, process_upload
from infrai_storage import Infrai
import os


async def run(image_path: Path, player_id: str, asset_id: str) -> None:
    api_key = os.environ["INFRAI_API_KEY"]
    async with httpx.AsyncClient(timeout=30) as client:
        infrai = Infrai(api_key, client)
        await infrai.storage.bucket.create(name=BUCKET)
        result = await process_upload(
            AssetUpload(
                asset_id=asset_id,
                player_id=player_id,
                content_type="image/jpeg",
                data_base64=base64.b64encode(image_path.read_bytes()).decode("ascii"),
            ),
            InfraiAssetStore(infrai, client),
        )
        print(result.model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Resize and store one player image")
    parser.add_argument("image", type=Path)
    parser.add_argument("--player", required=True)
    parser.add_argument("--asset", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.image, args.player, args.asset))


if __name__ == "__main__":
    main()

