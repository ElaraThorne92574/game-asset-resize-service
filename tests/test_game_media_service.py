import base64
import io

import pytest
from PIL import Image

from game_media_service import AssetUpload, ModerationState, process_upload


class RecordingStore:
    def __init__(self) -> None:
        self.saved: dict[str, object] = {}

    async def put(self, **values: object) -> None:
        self.saved = values


@pytest.mark.asyncio
async def test_live_event_image_is_resized_and_queued_for_review() -> None:
    source = io.BytesIO()
    Image.new("RGB", (3200, 1800), "#d43f3a").save(source, format="PNG")
    store = RecordingStore()

    result = await process_upload(
        AssetUpload(
            asset_id="banner-42",
            player_id="player-7",
            live_event_id="summer-cup",
            content_type="image/png",
            data_base64=base64.b64encode(source.getvalue()).decode("ascii"),
            send_to_moderation=True,
        ),
        store,
    )

    assert (result.width, result.height) == (1600, 900)
    assert result.moderation_state == ModerationState.QUEUED
    assert result.moderation_queue == "player-image-review"
    assert result.object_key == "players/player-7/summer-cup/banner-42.jpg"
    assert store.saved["content_type"] == "image/jpeg"
    with Image.open(io.BytesIO(store.saved["content"])) as saved:
        assert saved.size == (1600, 900)

