import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import post_next_tumblr


def test_load_state_returns_default_when_missing(tmp_path: Path):
    queue_path = (tmp_path / "generated_posts.json").resolve()
    state_path = tmp_path / "tumblr_post_state.json"

    state = post_next_tumblr.load_state(state_path, str(queue_path))

    assert state["last_posted_index"] == 0
    assert state["source_json_path"] == str(queue_path)
    assert state["history"] == []


def test_extract_tags_deduplicates_case_insensitively():
    tags = post_next_tumblr.extract_tags("Jai Ma. #ghargharkali #Mahakali #ghargharkali #mahakali")

    assert tags == ["ghargharkali", "Mahakali"]


def test_normalize_api_base_rejects_non_https():
    try:
        post_next_tumblr.normalize_api_base("http://api.tumblr.com")
    except RuntimeError as exc:
        assert str(exc) == "TUMBLR_API_BASE must be an https URL."
    else:
        raise AssertionError("Expected RuntimeError for non-https host")


def test_summarize_api_error_uses_meta_message():
    body = json.dumps({"meta": {"status": 401, "msg": "Unauthorized"}}).encode("utf-8")
    error = urllib.error.HTTPError(
        url="https://api.tumblr.com/v2/blog/example/posts",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )
    error.read = lambda: body

    assert post_next_tumblr.summarize_api_error(error) == "Tumblr API error 401: Unauthorized"


def test_publish_post_sends_text_and_tags(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        post_next_tumblr,
        "create_access_token",
        lambda: ("https://api.tumblr.com", "kakakaforadyakali.tumblr.com", "token-123"),
    )

    def fake_request_json(url: str, payload: dict, headers: dict | None = None) -> dict:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return {"response": {"id": "1234567890"}}

    monkeypatch.setattr(post_next_tumblr, "request_json", fake_request_json)

    post_id, post_url, tags = post_next_tumblr.publish_post("Today's name is Kali. Jai Ma. #ghargharkali")

    assert post_id == "1234567890"
    assert post_url == "https://kakakaforadyakali.tumblr.com/post/1234567890"
    assert tags == ["ghargharkali"]
    assert captured["url"] == "https://api.tumblr.com/v2/blog/kakakaforadyakali.tumblr.com/posts"
    assert captured["payload"]["content"] == [{"type": "text", "text": "Today's name is Kali. Jai Ma. #ghargharkali"}]
    assert captured["payload"]["tags"] == "ghargharkali"
    assert captured["payload"]["state"] == "published"
    assert captured["headers"]["Authorization"] == "Bearer token-123"


def test_main_posts_next_record_and_updates_state(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "generated_posts.json"
    queue_path.write_text(
        json.dumps(
            [
                {"index": 1, "post_text": "post one #alpha", "fits_length_limit": True},
                {"index": 2, "post_text": "post two #beta", "fits_length_limit": True},
            ]
        ),
        encoding="utf-8",
    )

    state_path = tmp_path / "tumblr_post_state.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "source_json_path": str(queue_path.resolve()),
                "last_posted_index": 1,
                "posted_post_ids": ["111"],
                "posted_post_urls": ["https://example.tumblr.com/post/111"],
                "posted_timestamps": ["2026-01-01T00:00:00+00:00"],
                "posted_text_hashes": ["abc"],
                "posted_tags": [["alpha"]],
                "history": [
                    {
                        "queue_index": 1,
                        "source_index": 1,
                        "post_id": "111",
                        "post_url": "https://example.tumblr.com/post/111",
                        "posted_at": "2026-01-01T00:00:00+00:00",
                        "text_hash": "abc",
                        "tags": ["alpha"],
                        "post_text": "post one #alpha",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        post_next_tumblr,
        "publish_post",
        lambda text: ("222", "https://example.tumblr.com/post/222", ["beta"]),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_next_tumblr.py",
            "--json",
            str(queue_path),
            "--state",
            str(state_path),
        ],
    )

    post_next_tumblr.main()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_posted_index"] == 2
    assert state["posted_post_ids"][-1] == "222"
    assert state["posted_post_urls"][-1] == "https://example.tumblr.com/post/222"
    assert state["posted_tags"][-1] == ["beta"]
    assert state["history"][-1]["queue_index"] == 2
    assert state["history"][-1]["post_text"] == "post two #beta"


def test_main_exits_cleanly_when_queue_complete(tmp_path: Path, monkeypatch, capsys):
    queue_path = tmp_path / "generated_posts.json"
    queue_path.write_text(
        json.dumps([{"index": 1, "post_text": "post one", "fits_length_limit": True}]),
        encoding="utf-8",
    )

    state_path = tmp_path / "tumblr_post_state.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "source_json_path": str(queue_path.resolve()),
                "last_posted_index": 1,
                "posted_post_ids": ["111"],
                "posted_post_urls": ["https://example.tumblr.com/post/111"],
                "posted_timestamps": ["2026-01-01T00:00:00+00:00"],
                "posted_text_hashes": ["abc"],
                "posted_tags": [["alpha"]],
                "history": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_next_tumblr.py",
            "--json",
            str(queue_path),
            "--state",
            str(state_path),
        ],
    )

    post_next_tumblr.main()

    captured = capsys.readouterr()
    assert "Queue complete. No Tumblr post published." in captured.out
