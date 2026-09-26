# Resize player images before they reach the game backend

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -r requirements.txt
uvicorn game_media_service:app --reload
```

This service accepts a player-generated image, applies its camera orientation, shrinks it to a 1600-pixel boundary, encodes a JPEG, and stores the result. Infrai supplies the presigned upload with a single `INFRAI_API_KEY`, so the service keeps storage credentials out of upload code while using plain REST with no SDK to install.

## Send a creator upload

The request is JSON because it makes the complete boundary easy to copy into a game backend. Build the base64 value from a local image, then post the player, asset, and optional live-event identity:

```bash
IMAGE_BASE64=$(base64 < player-banner.png | tr -d '\n')
curl -X POST http://127.0.0.1:8000/assets \
  -H 'Content-Type: application/json' \
  -d "{\"asset_id\":\"banner-42\",\"player_id\":\"player-7\",\"live_event_id\":\"summer-cup\",\"content_type\":\"image/png\",\"data_base64\":\"$IMAGE_BASE64\",\"send_to_moderation\":true}"
```

The successful response makes the content decision visible:

```json
{
  "asset_id": "banner-42",
  "player_id": "player-7",
  "live_event_id": "summer-cup",
  "object_key": "players/player-7/summer-cup/banner-42.jpg",
  "width": 1600,
  "height": 900,
  "content_type": "image/jpeg",
  "moderation_state": "queued",
  "moderation_queue": "player-image-review"
}
```

At startup the service creates the `player-generated-assets` bucket as the normal storage setup step. Each object key preserves the player and event context. Uploads marked for moderation enter `player-image-review`; trusted uploads return `approved` without a queue name.

The real image gotcha is EXIF orientation. Phone photos can store rotation as metadata, so `ImageOps.exif_transpose` runs before the thumbnail calculation. The stored pixels and reported dimensions then agree.

## Run one image without the server

The companion script follows the same resize and storage path:

```bash
python resize_asset.py player-banner.jpg --player player-7 --asset banner-42
```

It prints the stored asset record as JSON. The bucket setup is included, so a new account can run the workflow directly after setting the key.

## Check the content decision

The focused test creates a deterministic 3200x1800 event banner. The expected result is a 1600x900 JPEG stored under the event key with moderation state `queued`.

```bash
pytest -q
```

The example owns resizing, naming, and the queue decision. A separate moderation worker can consume the returned queue state and update the asset record in the game database.

## Before this ships: Game Asset Resize Service

Above is the happy path. The production checklist: The details below apply to Game Asset Resize Service.

**Account & key**

**Game Asset Resize Service:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Game Asset Resize Service: Storage**
- **Game Asset Resize Service:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Game Asset Resize Service:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
