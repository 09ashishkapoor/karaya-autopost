import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_posts import (
    build_records,
    load_config,
    parse_entries,
    parse_line,
    render_post,
    write_csv,
    write_json,
)


def test_load_config_resolves_paths_relative_to_config_directory(tmp_path: Path):
    config_path = tmp_path / "post_config.json"
    config_path.write_text(
        json.dumps(
            {
                "input_file": "input.txt",
                "post_template": "Today's name is {name}. {meaning} Jai Ma.",
                "csv_output": "output/posts.csv",
                "json_output": "output/posts.json",
                "max_length": 300,
            }
        ),
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert Path(config["input_file"]) == (tmp_path / "input.txt").resolve()
    assert Path(config["csv_output"]) == (tmp_path / "output" / "posts.csv").resolve()
    assert Path(config["json_output"]) == (tmp_path / "output" / "posts.json").resolve()


def test_parse_line_accepts_plain_format():
    assert parse_line("Bhairavaaya: Destroys fear.") == {
        "name": "Bhairavaaya",
        "meaning": "Destroys fear.",
    }


def test_parse_line_accepts_numbered_format():
    assert parse_line("12. Kali: The Black Goddess.") == {
        "name": "Kali",
        "meaning": "The Black Goddess.",
    }


def test_parse_line_rejects_missing_colon():
    assert parse_line("No separator here") is None


def test_parse_entries_returns_entries_and_skipped_lines():
    entries, skipped = parse_entries(
        "Bhairavaaya: Destroys fear.\n\nBad line\n2. Kali: The Black Goddess.\n"
    )

    assert entries == [
        {"index": 1, "name": "Bhairavaaya", "meaning": "Destroys fear."},
        {"index": 2, "name": "Kali", "meaning": "The Black Goddess."},
    ]
    assert skipped == [(3, "Bad line")]


def test_render_post_uses_template_fields():
    post = render_post(
        {"index": 7, "name": "Kali", "meaning": "The Black Goddess."},
        "Today's name is {name}. {meaning} Jai Ma.",
    )

    assert post == "Today's name is Kali. The Black Goddess. Jai Ma."


def test_build_records_marks_limit_status():
    records = build_records(
        [{"index": 1, "name": "Kali", "meaning": "Short meaning."}],
        {
            "post_template": "Today's name is {name}. {meaning} Jai Ma.",
            "max_length": 20,
            "input_file": "post_creator/input.txt",
        },
    )

    assert records[0]["character_count"] > 20
    assert records[0]["fits_length_limit"] is False


def test_write_csv_and_json_create_output_files(tmp_path: Path):
    records = [
        {
            "index": 1,
            "name": "Kali",
            "meaning": "The Black Goddess.",
            "post_text": "Today's name is Kali. The Black Goddess. Jai Ma.",
            "character_count": 52,
            "fits_length_limit": True,
            "source_file": "post_creator/input.txt",
        }
    ]

    csv_path = tmp_path / "posts.csv"
    json_path = tmp_path / "posts.json"

    write_csv(records, csv_path)
    write_json(records, json_path)

    assert csv_path.exists()
    assert json_path.exists()
    assert "post_text" in csv_path.read_text(encoding="utf-8")
    assert '"name": "Kali"' in json_path.read_text(encoding="utf-8")
