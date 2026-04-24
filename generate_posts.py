import argparse
import csv
import json
import re
from pathlib import Path


NUMBERED_LINE_RE = re.compile(r"^\s*\d+\.\s*")
REQUIRED_CONFIG_FIELDS = {
    "input_file",
    "post_template",
    "csv_output",
    "json_output",
}
CSV_FIELDS = [
    "index",
    "name",
    "meaning",
    "post_text",
    "character_count",
    "fits_length_limit",
    "source_file",
]


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_config(path: str) -> dict:
    config_path = Path(path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_CONFIG_FIELDS - config.keys())
    if missing:
        raise ValueError(f"Missing config fields: {', '.join(missing)}")

    base_dir = config_path.parent
    config["input_file"] = str(resolve_path(config["input_file"], base_dir))
    config["csv_output"] = str(resolve_path(config["csv_output"], base_dir))
    config["json_output"] = str(resolve_path(config["json_output"], base_dir))
    config["max_length"] = int(config.get("max_length", 280))
    return config


def parse_line(raw_line: str) -> dict | None:
    line = NUMBERED_LINE_RE.sub("", raw_line.strip())
    if not line or ":" not in line:
        return None

    name, meaning = [part.strip() for part in line.split(":", 1)]
    if not name or not meaning:
        return None
    return {"name": name, "meaning": meaning}


def parse_entries(text: str) -> tuple[list[dict], list[tuple[int, str]]]:
    entries = []
    skipped = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        parsed = parse_line(raw_line)
        if parsed is None:
            skipped.append((line_number, stripped))
            continue

        entries.append(
            {
                "index": len(entries) + 1,
                "name": parsed["name"],
                "meaning": parsed["meaning"],
            }
        )
    return entries, skipped


def render_post(entry: dict, template: str) -> str:
    return template.format(**entry)


def build_records(entries: list[dict], config: dict) -> list[dict]:
    records = []
    max_length = config["max_length"]
    for entry in entries:
        post_text = render_post(entry, config["post_template"])
        records.append(
            {
                "index": entry["index"],
                "name": entry["name"],
                "meaning": entry["meaning"],
                "post_text": post_text,
                "character_count": len(post_text),
                "fits_length_limit": len(post_text) <= max_length,
                "source_file": config["input_file"],
            }
        )
    return records


def write_csv(records: list[dict], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def write_json(records: list[dict], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate structured post output from one source text file."
    )
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    text = Path(config["input_file"]).read_text(encoding="utf-8")
    entries, skipped = parse_entries(text)
    records = build_records(entries, config)
    write_csv(records, config["csv_output"])
    write_json(records, config["json_output"])

    over_limit = sum(1 for record in records if not record["fits_length_limit"])
    print(f"Generated {len(records)} posts.")
    print(f"CSV: {config['csv_output']}")
    print(f"JSON: {config['json_output']}")
    print(f"Over limit: {over_limit}")
    if skipped:
        print(f"Skipped malformed lines: {len(skipped)}")


if __name__ == "__main__":
    main()
