import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import post_next_bluesky


def test_load_state_returns_default_when_missing(tmp_path: Path):
    queue_path = (tmp_path / "generated_posts.json").resolve()
    state_path = tmp_path / "bluesky_post_state.json"

    state = post_next_bluesky.load_state(state_path, str(queue_path))

    assert state["last_posted_index"] == 0
    assert state["source_json_path"] == str(queue_path)


def test_load_state_supports_utf8_bom(tmp_path: Path):
    queue_path = (tmp_path / "generated_posts.json").resolve()
    state_path = tmp_path / "bluesky_post_state.json"
    content = json.dumps({"last_posted_index": 2})
    state_path.write_bytes(content.encode("utf-8-sig"))

    state = post_next_bluesky.load_state(state_path, str(queue_path))

    assert state["last_posted_index"] == 2


def test_load_state_drops_legacy_history(tmp_path: Path):
    state_path = tmp_path / "bluesky_post_state.json"
    state_path.write_text(
        json.dumps(
            {
                "last_posted_index": 5,
                "posted_cids": ["old"],
                "history": [{"queue_index": 5, "post_text": "old"}],
            }
        ),
        encoding="utf-8",
    )

    state = post_next_bluesky.load_state(state_path, "queue.json")

    assert state == {"version": 1, "source_json_path": "queue.json", "last_posted_index": 5}


def test_next_queue_position_wraps_after_last_record():
    state = {"last_posted_index": 3}

    assert post_next_bluesky.next_queue_position(state, queue_size=3) == 1
    assert post_next_bluesky.next_queue_position(state, queue_size=4) == 4
    assert post_next_bluesky.next_queue_position({"last_posted_index": 1}, queue_size=3) == 2


def test_next_queue_position_returns_none_for_empty_queue():
    assert post_next_bluesky.next_queue_position({"last_posted_index": 0}, queue_size=0) is None


def test_next_queue_position_rejects_shrunk_queue():
    state = {"last_posted_index": 5}

    try:
        post_next_bluesky.next_queue_position(state, queue_size=3)
    except RuntimeError as exc:
        assert "beyond the queue size" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when state is past the queue end")


def test_normalize_pds_host_rejects_non_https():
    try:
        post_next_bluesky.normalize_pds_host("http://bsky.social")
    except RuntimeError as exc:
        assert str(exc) == "BLUESKY_PDS_HOST must be an https URL."
    else:
        raise AssertionError("Expected RuntimeError for non-https host")


def test_normalize_pds_host_rejects_endpoint_path():
    try:
        post_next_bluesky.normalize_pds_host("https://bsky.social/xrpc/com.atproto.server.createSession")
    except RuntimeError as exc:
        assert str(exc) == "BLUESKY_PDS_HOST must be a host root, not a full endpoint path."
    else:
        raise AssertionError("Expected RuntimeError for endpoint path")


def test_summarize_api_error_uses_safe_message():
    body = json.dumps({"error": "AuthMissing", "message": "Authentication Required"}).encode("utf-8")
    error = urllib.error.HTTPError(
        url="https://bsky.social/xrpc/test",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )
    error.read = lambda: body

    assert (
        post_next_bluesky.summarize_api_error(error)
        == "Bluesky API error 401: AuthMissing - Authentication Required"
    )


def test_main_posts_next_record_and_updates_state(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "generated_posts.json"
    queue_path.write_text(
        json.dumps(
            [
                {"index": 1, "post_text": "post one", "fits_length_limit": True},
                {"index": 2, "post_text": "post two", "fits_length_limit": True},
            ]
        ),
        encoding="utf-8",
    )

    state_path = tmp_path / "bluesky_post_state.json"
    state_path.write_text(json.dumps({"last_posted_index": 1}), encoding="utf-8")

    monkeypatch.setattr(post_next_bluesky, "publish_post", lambda text: ("at://second", "cid2"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_next_bluesky.py",
            "--json",
            str(queue_path),
            "--state",
            str(state_path),
        ],
    )

    post_next_bluesky.main()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_posted_index"] == 2
    assert "history" not in state


def test_main_wraps_and_posts_first_record_again(tmp_path: Path, monkeypatch, capsys):
    queue_path = tmp_path / "generated_posts.json"
    queue_path.write_text(
        json.dumps([{"index": 1, "post_text": "post one", "fits_length_limit": True}]),
        encoding="utf-8",
    )

    state_path = tmp_path / "bluesky_post_state.json"
    state_path.write_text(json.dumps({"last_posted_index": 1}), encoding="utf-8")

    monkeypatch.setattr(post_next_bluesky, "publish_post", lambda text: ("at://wrapped", "cidw"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_next_bluesky.py",
            "--json",
            str(queue_path),
            "--state",
            str(state_path),
        ],
    )

    post_next_bluesky.main()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_posted_index"] == 1
    assert "Posted queue index 1/1 to Bluesky" in capsys.readouterr().out
