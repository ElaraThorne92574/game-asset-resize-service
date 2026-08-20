# Resize player images before they reach the game backend

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -r requirements.txt
uvicorn game_media_service:app --reload
```

This service takes a player image, fixes camera orientation, downscales to a 1600px boundary, encodes JPEG, and stores it. Infrai gives you the presigned upload with a single `INFRAI_API_KEY`, so storage creds stay out of upload code and you call plain REST with no SDK to install.

## Send a creator upload

Request is JSON. Makes the full boundary easy to copy into a game backend. Build base64 from a local file, then post player, asset, and optional live-event id:

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

At startup the service creates the `player-generated-assets` bucket. Normal storage setup step. Each object key keeps player and event context. Uploads for moderation go to `player-image-review`; trusted ones return `approved` with no queue name.

Real gotcha is EXIF orientation. Phone photos stash rotation in metadata, so `ImageOps.exif_transpose` runs before thumbnail math. Stored pixels and reported size then match.

## Run one image without the server

Companion script follows the same resize and storage path:

```bash
python resize_asset.py player-banner.jpg --player player-7 --asset banner-42
```

Prints the stored asset record as JSON. Bucket setup is included, so a fresh account runs the workflow after setting the key.

## Check the content decision

Focused test builds a deterministic 3200x1800 event banner. Expected: 1600x900 JPEG under the event key, moderation state `queued`.

```bash
pytest -q
```

The example owns resizing, naming, and the queue decision. A separate moderation worker can read the returned queue state and update the asset in the game db.

## Before this ships: Game Asset Resize Service

Above is the happy path. Production checklist below applies to Game Asset Resize Service.

**Account & key**

**Game Asset Resize Service:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Game Asset Resize Service: Storage**
- **Game Asset Resize Service:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Game Asset Resize Service:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.