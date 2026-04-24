import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


STATE_VERSION = 1
DEFAULT_API_BASE = "https://api.tumblr.com"
DEFAULT_USER_AGENT = "karaya-autopost-tumblr/1.0"
HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")


def summarize_api_error(exc: urllib.error.HTTPError) -> str:
    details = exc.read().decode("utf-8", errors="replace")
    try:
        body = json.loads(details)
    except json.JSONDecodeError:
        return f"Tumblr API error {exc.code}."

    meta = body.get("meta") if isinstance(body, dict) else None
    errors = body.get("errors") if isinstance(body, dict) else None
    if isinstance(meta, dict):
        msg = meta.get("msg")
        if msg:
            return f"Tumblr API error {exc.code}: {msg}"
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, str) and first:
            return f"Tumblr API error {exc.code}: {first}"
        if isinstance(first, dict):
            detail = first.get("detail") or first.get("title")
            if detail:
                return f"Tumblr API error {exc.code}: {detail}"
    return f"Tumblr API error {exc.code}."


def normalize_api_base(value: str) -> str:
    normalized = (value or DEFAULT_API_BASE).strip().rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("TUMBLR_API_BASE must be an https URL.")
    if parsed.params or parsed.query or parsed.fragment:
        raise RuntimeError("TUMBLR_API_BASE must not include params, query, or fragment.")
    if parsed.path not in ("", "/"):
        raise RuntimeError("TUMBLR_API_BASE must be a host root, not a full endpoint path.")
    return f"{parsed.scheme}://{parsed.netloc}"


def request_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": os.environ.get("TUMBLR_USER_AGENT", DEFAULT_USER_AGENT),
            **(headers or {}),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(summarize_api_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while calling Tumblr API: {exc.reason}") from exc

    return json.loads(raw)


def request_form(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": os.environ.get("TUMBLR_USER_AGENT", DEFAULT_USER_AGENT),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(summarize_api_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while calling Tumblr API: {exc.reason}") from exc

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
        "encrypted_refresh_token": "",
        "posted_post_ids": [],
        "posted_post_urls": [],
        "posted_timestamps": [],
        "posted_text_hashes": [],
        "posted_tags": [],
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
        "posted_post_ids",
        "posted_post_urls",
        "posted_timestamps",
        "posted_text_hashes",
        "posted_tags",
        "history",
    ]:
        value = loaded.get(key)
        if not isinstance(value, list):
            raise ValueError(f"State field '{key}' must be a list.")
    if not isinstance(loaded.get("encrypted_refresh_token", ""), str):
        raise ValueError("State field 'encrypted_refresh_token' must be a string.")

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


def derive_refresh_token_key(client_secret: str) -> bytes:
    return hashlib.sha256(f"tumblr-refresh-token:{client_secret}".encode("utf-8")).digest()


def build_keystream(secret_key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        counter_bytes = counter.to_bytes(4, "big")
        blocks.append(hmac.new(secret_key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def encrypt_refresh_token(refresh_token: str, client_secret: str) -> str:
    secret_key = derive_refresh_token_key(client_secret)
    nonce = os.urandom(16)
    plaintext = refresh_token.encode("utf-8")
    keystream = build_keystream(secret_key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream))
    mac = hmac.new(secret_key, nonce + ciphertext, hashlib.sha256).digest()
    payload = {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "mac": base64.b64encode(mac).decode("ascii"),
    }
    return json.dumps(payload, separators=(",", ":"))


def decrypt_refresh_token(encrypted_value: str, client_secret: str) -> str:
    if not encrypted_value:
        return ""
    try:
        payload = json.loads(encrypted_value)
        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ciphertext"])
        received_mac = base64.b64decode(payload["mac"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Tumblr state contains an invalid encrypted refresh token payload.") from exc

    secret_key = derive_refresh_token_key(client_secret)
    expected_mac = hmac.new(secret_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(received_mac, expected_mac):
        raise RuntimeError("Tumblr state refresh token could not be verified with the current client secret.")

    keystream = build_keystream(secret_key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream))
    return plaintext.decode("utf-8")


def extract_tags(text: str) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for match in HASHTAG_PATTERN.finditer(text):
        tag = match.group(1)
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def resolve_refresh_token(state: dict, client_secret: str) -> str:
    stored_token = decrypt_refresh_token(state.get("encrypted_refresh_token", ""), client_secret)
    if stored_token:
        return stored_token

    bootstrap_token = os.environ.get("TUMBLR_REFRESH_TOKEN", "").strip()
    if bootstrap_token:
        return bootstrap_token

    raise RuntimeError("Missing Tumblr refresh token. Set TUMBLR_REFRESH_TOKEN or restore state token data.")


def create_access_token(state: dict) -> tuple[str, str, str, str]:
    client_id = os.environ.get("TUMBLR_CLIENT_ID", "").strip()
    client_secret = os.environ.get("TUMBLR_CLIENT_SECRET", "").strip()
    blog_identifier = os.environ.get("TUMBLR_BLOG_IDENTIFIER", "").strip()
    api_base = os.environ.get("TUMBLR_API_BASE", DEFAULT_API_BASE)

    missing = [
        name
        for name, value in [
            ("TUMBLR_CLIENT_ID", client_id),
            ("TUMBLR_CLIENT_SECRET", client_secret),
            ("TUMBLR_BLOG_IDENTIFIER", blog_identifier),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    refresh_token = resolve_refresh_token(state, client_secret)
    normalized_api_base = normalize_api_base(api_base)
    response = request_form(
        f"{normalized_api_base}/v2/oauth2/token",
        payload={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )

    access_token = response.get("access_token")
    rotated_refresh_token = response.get("refresh_token") or refresh_token
    if not access_token:
        raise RuntimeError(f"Tumblr token response missing access_token: {json.dumps(response, ensure_ascii=False)}")

    return normalized_api_base, blog_identifier, str(access_token), str(rotated_refresh_token)


def publish_post(text: str, api_base: str, blog_identifier: str, access_token: str) -> tuple[str, str, list[str]]:
    tags = extract_tags(text)
    encoded_blog_identifier = urllib.parse.quote(blog_identifier, safe=":._-~")
    response = request_json(
        f"{api_base}/v2/blog/{encoded_blog_identifier}/posts",
        payload={
            "content": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
            "tags": ",".join(tags),
            "state": "published",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    body = response.get("response")
    if not isinstance(body, dict):
        raise RuntimeError(f"Tumblr API response missing response object: {json.dumps(response, ensure_ascii=False)}")

    post_id = body.get("id")
    if not post_id:
        raise RuntimeError(f"Tumblr API response missing post id: {json.dumps(response, ensure_ascii=False)}")

    post_url = f"https://{blog_identifier}/post/{post_id}"
    return str(post_id), post_url, tags


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post next Tumblr record from queue JSON in strict order.")
    parser.add_argument("--json", required=True, help="Path to generated post queue JSON.")
    parser.add_argument("--state", default="output/tumblr_post_state.json", help="Path to persistent Tumblr state JSON.")
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
        print("Queue complete. No Tumblr post published.")
        return

    record = queue[position - 1]
    post_text = record["post_text"].strip()
    if record.get("fits_length_limit") is False:
        raise RuntimeError(f"Post at queue index {position} exceeds the configured length limit.")

    api_base, blog_identifier, access_token, rotated_refresh_token = create_access_token(state)
    state["encrypted_refresh_token"] = encrypt_refresh_token(
        rotated_refresh_token,
        os.environ.get("TUMBLR_CLIENT_SECRET", "").strip(),
    )
    save_state(state_path, state)

    post_id, post_url, tags = publish_post(post_text, api_base, blog_identifier, access_token)

    posted_at = datetime.now(timezone.utc).isoformat()
    text_hash = sha256_text(post_text)

    state["version"] = STATE_VERSION
    state["source_json_path"] = str(queue_path)
    state["last_posted_index"] = position
    state["posted_post_ids"].append(post_id)
    state["posted_post_urls"].append(post_url)
    state["posted_timestamps"].append(posted_at)
    state["posted_text_hashes"].append(text_hash)
    state["posted_tags"].append(tags)
    state["history"].append(
        {
            "queue_index": position,
            "source_index": record.get("index"),
            "post_id": post_id,
            "post_url": post_url,
            "posted_at": posted_at,
            "text_hash": text_hash,
            "tags": tags,
            "post_text": post_text,
        }
    )

    save_state(state_path, state)
    print(f"Posted queue index {position}/{len(queue)} to Tumblr. Post ID: {post_id}")


if __name__ == "__main__":
    main()
