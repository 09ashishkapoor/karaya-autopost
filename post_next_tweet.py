import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.x.com/2/tweets"
STATE_VERSION = 1


def percent_encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~-._")


def build_oauth1_header(method: str, url: str, consumer_key: str, consumer_secret: str, token: str, token_secret: str) -> str:
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }

    encoded_pairs = []
    for key, value in oauth_params.items():
        encoded_pairs.append((percent_encode(key), percent_encode(value)))
    encoded_pairs.sort()
    normalized = "&".join(f"{key}={value}" for key, value in encoded_pairs)

    base_string = "&".join(
        [
            method.upper(),
            percent_encode(url),
            percent_encode(normalized),
        ]
    )

    signing_key = f"{percent_encode(consumer_secret)}&{percent_encode(token_secret)}"
    signature_digest = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    oauth_params["oauth_signature"] = base64.b64encode(signature_digest).decode("ascii")

    header_params = ", ".join(
        f'{percent_encode(key)}="{percent_encode(value)}"'
        for key, value in sorted(oauth_params.items())
    )
    return f"OAuth {header_params}"


def load_queue(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Queue JSON not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("Queue JSON must be a list of tweet records.")

    for idx, record in enumerate(data, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Record {idx} is not an object.")
        if "tweet_text" not in record:
            raise ValueError(f"Record {idx} missing required field 'tweet_text'.")
        if not isinstance(record["tweet_text"], str) or not record["tweet_text"].strip():
            raise ValueError(f"Record {idx} has empty 'tweet_text'.")
    return data


def default_state(source_json_path: str) -> dict:
    return {
        "version": STATE_VERSION,
        "source_json_path": source_json_path,
        "last_posted_index": 0,
        "posted_tweet_ids": [],
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

    for key in ["posted_tweet_ids", "posted_timestamps", "posted_text_hashes", "history"]:
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


def post_tweet(text: str) -> str:
    consumer_key = os.environ.get("X_API_KEY", "").strip()
    consumer_secret = os.environ.get("X_API_SECRET", "").strip()
    access_token = os.environ.get("X_ACCESS_TOKEN", "").strip()
    access_token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "").strip()

    missing = [
        name
        for name, value in [
            ("X_API_KEY", consumer_key),
            ("X_API_SECRET", consumer_secret),
            ("X_ACCESS_TOKEN", access_token),
            ("X_ACCESS_TOKEN_SECRET", access_token_secret),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    authorization = build_oauth1_header(
        method="POST",
        url=API_URL,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token=access_token,
        token_secret=access_token_secret,
    )

    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"X API error {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while calling X API: {exc.reason}") from exc

    body = json.loads(raw)
    tweet_id = body.get("data", {}).get("id")
    if not tweet_id:
        raise RuntimeError(f"X API response missing tweet id: {raw}")
    return str(tweet_id)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post next tweet from queue JSON in strict order.")
    parser.add_argument("--json", required=True, help="Path to generated tweet queue JSON.")
    parser.add_argument("--state", default="output/post_state.json", help="Path to persistent state JSON.")
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
        print("Queue complete. No tweet posted.")
        return

    record = queue[position - 1]
    tweet_text = record["tweet_text"].strip()
    if len(tweet_text) > 280:
        raise RuntimeError(f"Tweet at queue index {position} exceeds 280 chars.")

    tweet_id = post_tweet(tweet_text)

    posted_at = datetime.now(timezone.utc).isoformat()
    text_hash = sha256_text(tweet_text)

    state["version"] = STATE_VERSION
    state["source_json_path"] = str(queue_path)
    state["last_posted_index"] = position
    state["posted_tweet_ids"].append(tweet_id)
    state["posted_timestamps"].append(posted_at)
    state["posted_text_hashes"].append(text_hash)
    state["history"].append(
        {
            "queue_index": position,
            "source_index": record.get("index"),
            "tweet_id": tweet_id,
            "posted_at": posted_at,
            "text_hash": text_hash,
            "tweet_text": tweet_text,
        }
    )

    save_state(state_path, state)
    print(f"Posted queue index {position}/{len(queue)}. Tweet ID: {tweet_id}")


if __name__ == "__main__":
    main()
