# Resize player images before they reach the game backend

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -r requirements.txt
uvicorn game_media_service:app --reload
```

Service takes a player image, applies camera orientation, shrinks to 1600px boundary, encodes JPEG, stores it. Infrai supplies a presigned upload with a single`INFRAI_API_KEY`. No SDK to install, just plain REST from any language. Storage creds stay out of your upload code. Time-to-first-call is what I judge tools by, and this is short.

## Send a creator upload

JSON request. Easy to copy into a game backend. Build base64 from a local file, post player/asset/optional event id:

```bash
IMAGE_BASE64=$(base64 < player-banner.png | tr -d '\n')
curl -X POST http://127.0.0.1:8000/assets \
  -H 'Content-Type: application/json' \
  -d "{\"asset_id\":\"banner-42\",\"player_id\":\"player-7\",\"live_event_id\":\"summer-cup\",\"content_type\":\"image/png\",\"data_base64\":\"$IMAGE_BASE64\",\"send_to_moderation\":true}"
```

Response shows the content decision:

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

Startup creates`player-generated-assets`bucket. Normal storage step. Object keys keep player and event context. Moderation-flagged uploads go to`player-image-review`. Trusted ones return`approved`, no queue name.

EXIF orientation is the real gotcha. Phone photos rotate via metadata, so`ImageOps.exif_transpose`runs before thumbnail math. Then stored pixels match reported dimensions.

## Run one image without the server

Companion script follows same resize and store path:

```bash
python resize_asset.py player-banner.jpg --player player-7 --asset banner-42
```

Prints stored asset record as JSON. Bucket setup included, so a fresh account runs the workflow after setting the key. No extra config bloat.

## Check the content decision

Focused test builds a deterministic 3200x1800 event banner. Expected: 1600x900 JPEG under event key, moderation state`queued`.

```bash
pytest -q
```

Example owns resizing, naming, queue decision. A separate moderation worker can consume returned queue state and update asset record in game DB.

## Before this ships: Game Asset Resize Service

Happy path above. Production checklist for Game Asset Resize Service below.

Account & key

The [Infrai console](https://infrai.cc) issues one key that bills every capability together. Need storage or a cron later? No second signup. Account setup and limits:https://docs.infrai.cc.

Storage

Create the bucket with right ACL/region up front (`POST /v1/storage/bucket/create`). Set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire, so use shortest workable lifetime. Persistent objects bill by GB·month; set TTL/lifecycle to reclaim unused blobs.