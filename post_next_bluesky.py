import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


STATE_VERSION = 1
DEFAULT_PDS_HOST = "https://bsky.social"


def request_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bluesky API error {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while calling Bluesky API: {exc.reason}") from exc

    return json.loads(raw)


def load_queue(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Queue JSON not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("Queue JSON must be a list of post records.")

    for idx, record in enumerate(data, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Record {idx} is not an object.")
        if "post_text" not in record:
            raise ValueError(f"Record {idx} missing required field 'post_text'.")
        if not isinstance(record["post_text"], str) or not record["post_text"].strip():
            raise ValueError(f"Record {idx} has empty 'post_text'.")
    return data


def default_state(source_json_path: str) -> dict:
    return {
        "version": STATE_VERSION,
        "source_json_path": source_json_path,
        "last_posted_index": 0,
        "posted_record_uris": [],
        "posted_cids": [],
        "posted_timestamps": [],
        "posted_text_hashes": [],
        "history": [],
    }


def load_state(path: Path, source_json_path: str) -> dict:
    if not path.exists():
        return default_state(source_json_path)

    state = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(state, dict):
        raise ValueError("State file must be a JSON object.")

    loaded = default_state(source_json_path)
    loaded.update(state)

    if loaded["source_json_path"] != source_json_path:
        loaded["source_json_path"] = source_json_path

    loaded["last_posted_index"] = int(loaded.get("last_posted_index", 0))
    if loaded["last_posted_index"] < 0:
        raise ValueError("last_posted_index cannot be negative.")

    for key in [
        "posted_record_uris",
        "posted_cids",
        "posted_timestamps",
        "posted_text_hashes",
        "history",
    ]:
        value = loaded.get(key)
        if not isinstance(value, list):
            raise ValueError(f"State field '{key}' must be a list.")

    return loaded


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def next_queue_position(state: dict, queue_size: int) -> int | None:
    next_index = int(state["last_posted_index"]) + 1
    if next_index > queue_size:
        return None
    return next_index


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_session() -> tuple[str, dict]:
    identifier = os.environ.get("BLUESKY_IDENTIFIER", "").strip()
    password = os.environ.get("BLUESKY_APP_PASSWORD", "").strip()
    pds_host = os.environ.get("BLUESKY_PDS_HOST", DEFAULT_PDS_HOST).strip() or DEFAULT_PDS_HOST

    missing = [
        name
        for name, value in [
            ("BLUESKY_IDENTIFIER", identifier),
            ("BLUESKY_APP_PASSWORD", password),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    normalized_host = pds_host.rstrip("/")
    session = request_json(
        f"{normalized_host}/xrpc/com.atproto.server.createSession",
        payload={
            "identifier": identifier,
            "password": password,
        },
    )
    return normalized_host, session


def publish_post(text: str) -> tuple[str, str]:
    pds_host, session = create_session()
    response = request_json(
        f"{pds_host}/xrpc/com.atproto.repo.createRecord",
        payload={
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        },
        headers={
            "Authorization": f"Bearer {session['accessJwt']}",
        },
    )

    post_uri = response.get("uri")
    cid = response.get("cid")
    if not post_uri or not cid:
        raise RuntimeError(f"Bluesky API response missing uri/cid: {json.dumps(response, ensure_ascii=False)}")
    return str(post_uri), str(cid)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post next Bluesky record from queue JSON in strict order.")
    parser.add_argument("--json", required=True, help="Path to generated post queue JSON.")
    parser.add_argument("--state", default="output/bluesky_post_state.json", help="Path to persistent Bluesky state JSON.")
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    queue_path = Path(args.json).resolve()
    state_path = Path(args.state).resolve()

    queue = load_queue(queue_path)
    state = load_state(state_path, str(queue_path))

    position = next_queue_position(state, len(queue))
    if position is None:
        print("Queue complete. No Bluesky post published.")
        return

    record = queue[position - 1]
    post_text = record["post_text"].strip()
    if record.get("fits_length_limit") is False:
        raise RuntimeError(f"Post at queue index {position} exceeds the configured length limit.")

    post_uri, cid = publish_post(post_text)

    posted_at = datetime.now(timezone.utc).isoformat()
    text_hash = sha256_text(post_text)

    state["version"] = STATE_VERSION
    state["source_json_path"] = str(queue_path)
    state["last_posted_index"] = position
    state["posted_record_uris"].append(post_uri)
    state["posted_cids"].append(cid)
    state["posted_timestamps"].append(posted_at)
    state["posted_text_hashes"].append(text_hash)
    state["history"].append(
        {
            "queue_index": position,
            "source_index": record.get("index"),
            "post_uri": post_uri,
            "cid": cid,
            "posted_at": posted_at,
            "text_hash": text_hash,
            "post_text": post_text,
        }
    )

    save_state(state_path, state)
    print(f"Posted queue index {position}/{len(queue)} to Bluesky. URI: {post_uri}")


if __name__ == "__main__":
    main()
