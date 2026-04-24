import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import post_next_tweet


def test_load_state_returns_default_when_missing(tmp_path: Path):
    queue_path = (tmp_path / "generated_tweets.json").resolve()
    state_path = tmp_path / "post_state.json"

    state = post_next_tweet.load_state(state_path, str(queue_path))

    assert state["last_posted_index"] == 0
    assert state["source_json_path"] == str(queue_path)
    assert state["history"] == []


def test_load_state_supports_utf8_bom(tmp_path: Path):
    queue_path = (tmp_path / "generated_tweets.json").resolve()
    state_path = tmp_path / "post_state.json"
    content = json.dumps({"last_posted_index": 2})
    state_path.write_bytes(content.encode("utf-8-sig"))

    state = post_next_tweet.load_state(state_path, str(queue_path))

    assert state["last_posted_index"] == 2


def test_next_queue_position_handles_completion():
    state = {"last_posted_index": 3}

    assert post_next_tweet.next_queue_position(state, queue_size=3) is None
    assert post_next_tweet.next_queue_position(state, queue_size=4) == 4


def test_main_posts_next_tweet_and_updates_state(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "generated_tweets.json"
    queue_path.write_text(
        json.dumps(
            [
                {"index": 1, "tweet_text": "tweet one"},
                {"index": 2, "tweet_text": "tweet two"},
            ]
        ),
        encoding="utf-8",
    )

    state_path = tmp_path / "post_state.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "source_json_path": str(queue_path.resolve()),
                "last_posted_index": 1,
                "posted_tweet_ids": ["111"],
                "posted_timestamps": ["2026-01-01T00:00:00+00:00"],
                "posted_text_hashes": ["abc"],
                "history": [
                    {
                        "queue_index": 1,
                        "source_index": 1,
                        "tweet_id": "111",
                        "posted_at": "2026-01-01T00:00:00+00:00",
                        "text_hash": "abc",
                        "tweet_text": "tweet one",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(post_next_tweet, "post_tweet", lambda text: "222")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_next_tweet.py",
            "--json",
            str(queue_path),
            "--state",
            str(state_path),
        ],
    )

    post_next_tweet.main()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_posted_index"] == 2
    assert state["posted_tweet_ids"][-1] == "222"
    assert state["history"][-1]["queue_index"] == 2
    assert state["history"][-1]["tweet_text"] == "tweet two"
