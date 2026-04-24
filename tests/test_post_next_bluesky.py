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
    assert state["history"] == []


def test_load_state_supports_utf8_bom(tmp_path: Path):
    queue_path = (tmp_path / "generated_posts.json").resolve()
    state_path = tmp_path / "bluesky_post_state.json"
    content = json.dumps({"last_posted_index": 2})
    state_path.write_bytes(content.encode("utf-8-sig"))

    state = post_next_bluesky.load_state(state_path, str(queue_path))

    assert state["last_posted_index"] == 2


def test_next_queue_position_handles_completion():
    state = {"last_posted_index": 3}

    assert post_next_bluesky.next_queue_position(state, queue_size=3) is None
    assert post_next_bluesky.next_queue_position(state, queue_size=4) == 4


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
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "source_json_path": str(queue_path.resolve()),
                "last_posted_index": 1,
                "posted_record_uris": ["at://first"],
                "posted_cids": ["cid1"],
                "posted_timestamps": ["2026-01-01T00:00:00+00:00"],
                "posted_text_hashes": ["abc"],
                "history": [
                    {
                        "queue_index": 1,
                        "source_index": 1,
                        "post_uri": "at://first",
                        "cid": "cid1",
                        "posted_at": "2026-01-01T00:00:00+00:00",
                        "text_hash": "abc",
                        "post_text": "post one",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

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
    assert state["posted_record_uris"][-1] == "at://second"
    assert state["posted_cids"][-1] == "cid2"
    assert state["history"][-1]["queue_index"] == 2
    assert state["history"][-1]["post_text"] == "post two"


def test_main_exits_cleanly_when_queue_complete(tmp_path: Path, monkeypatch, capsys):
    queue_path = tmp_path / "generated_posts.json"
    queue_path.write_text(
        json.dumps([{"index": 1, "post_text": "post one", "fits_length_limit": True}]),
        encoding="utf-8",
    )

    state_path = tmp_path / "bluesky_post_state.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "source_json_path": str(queue_path.resolve()),
                "last_posted_index": 1,
                "posted_record_uris": ["at://first"],
                "posted_cids": ["cid1"],
                "posted_timestamps": ["2026-01-01T00:00:00+00:00"],
                "posted_text_hashes": ["abc"],
                "history": [],
            }
        ),
        encoding="utf-8",
    )

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

    captured = capsys.readouterr()
    assert "Queue complete. No Bluesky post published." in captured.out
