# Karaya Autopost

Karaya Autopost is a small, dependency-free Python utility for turning devotional name-and-meaning text files into template-based CSV and JSON exports.

It was built for simple devotional posting workflows: keep source entries in plain text, choose a text template in JSON, and generate structured exports that can be reviewed, scheduled, or imported elsewhere.

## Features

- Parses plain `name: meaning` source files.
- Accepts numbered source lists such as `1. Kali: The Black Goddess`.
- Renders post text from a configurable template.
- Exports matching CSV and JSON records.
- Flags records that exceed a configurable character limit.
- Posts one queued text record at a time to Bluesky.
- Uses only the Python standard library at runtime.

## Repository Contents

- `generate_posts.py` - command-line generator and parsing/export helpers.
- `post_next_bluesky.py` - posts exactly one next Bluesky record from a generated JSON queue.
- `post_config.json` - Kalabhairava export configuration.
- `post_config_mahakali.json` - Mahakali export configuration.
- `.github/workflows/bluesky-autopost.yml` - every-30-minutes Bluesky workflow.
- `output/bluesky_post_state.json` - persistent Bluesky posting state committed back to the repo.
- `combined_kalabhairava_onelinemeanings_nosalutations_FULL_APRIL22.txt` - Kalabhairava source entries.
- `combined_mahakali_onelinemeanings__FULL_APRIL22.txt` - Mahakali source entries.
- `requirements-dev.txt` - development-only test dependency list.
- `tests/test_generate_posts.py` - pytest coverage for config loading, parsing, rendering, and file exports.
- `tests/test_post_next_bluesky.py` - pytest coverage for queue progression and Bluesky state handling.

## Requirements

- Python 3.10 or newer.
- `pytest` only if you want to run the test suite.

The generator itself uses only the Python standard library.

## Quick Start

Run commands from the repository root:

```bash
python generate_posts.py --config post_config.json
python generate_posts.py --config post_config_mahakali.json
```

By default, these write files under `output/`:

- `output/generated_posts.csv`
- `output/generated_posts.json`
- `output/generated_posts_mahakali.csv`
- `output/generated_posts_mahakali.json`

The script prints the number of generated records, output paths, how many entries exceed the configured length limit, and how many malformed source lines were skipped.

## Bluesky Autopost

This repo includes a production Bluesky autopost flow:

- queue source: `output/generated_posts.json`
- state file: `output/bluesky_post_state.json`
- schedule: every 30 minutes at minutes `17` and `47`
- posting order: first to last, no randomness
- posting mode: one text post per run

### Required GitHub Repository Secrets

Add these in `Settings -> Secrets and variables -> Actions`:

- `BLUESKY_IDENTIFIER`
- `BLUESKY_APP_PASSWORD`

Optional environment variable:

- `BLUESKY_PDS_HOST`
  Default: `https://bsky.social`

### Workflow Behavior

Workflow file: `.github/workflows/bluesky-autopost.yml`

- Runs on cron `17,47 * * * *` and supports manual `workflow_dispatch`.
- Uses workflow concurrency group `bluesky-autopost` to prevent overlapping posts.
- Calls:

```bash
python post_next_bluesky.py --json output/generated_posts.json --state output/bluesky_post_state.json
```

- Commits `output/bluesky_post_state.json` back to the repo only when state changes.

## Install for Development

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```

On macOS or Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Source File Format

Each valid source entry must contain a name and meaning separated by the first colon:

```text
Bhairavaaya: The one who is terrifying and who destroys fear.
```

Numbered lines are also accepted:

```text
1. Kali: The Black Goddess, ruler of Time.
```

Blank lines are ignored. Non-blank lines without a valid `name: meaning` shape are skipped and counted in the command output.

## Configuration

Each config file is JSON with these fields:

```json
{
  "input_file": "combined_kalabhairava_onelinemeanings_nosalutations_FULL_APRIL22.txt",
  "post_template": "Today's name is {name}. {meaning} Jai Bhairava.",
  "csv_output": "output/generated_posts.csv",
  "json_output": "output/generated_posts.json",
  "max_length": 300
}
```

Required fields:

- `input_file` - source text file to parse.
- `post_template` - Python format string used to render each post.
- `csv_output` - CSV export path.
- `json_output` - JSON export path.

Optional fields:

- `max_length` - character limit used for the `fits_length_limit` flag. Defaults to `300`.

Paths may be absolute or relative. Relative paths are resolved from the config file's directory.

Available template fields:

- `{index}` - 1-based entry number after skipped lines are removed.
- `{name}` - parsed devotional name.
- `{meaning}` - parsed one-line meaning.

## Output Schema

CSV and JSON records include:

- `index`
- `name`
- `meaning`
- `post_text`
- `character_count`
- `fits_length_limit`
- `source_file`

## Run Tests

```bash
python -m pytest -v
```

Current test coverage verifies path resolution, accepted input formats, malformed-line handling, template rendering, length-limit flags, CSV/JSON file creation, queue progression, and Bluesky state updates.

## Public Release Notes

- Most generated exports are ignored by git. The tracked queue/state files under `output/` are kept for automation.
- The included devotional source files are part of the project data. Before publishing or redistributing modified datasets, confirm that any added content can be shared publicly.
- Bluesky posting requires `BLUESKY_IDENTIFIER` and `BLUESKY_APP_PASSWORD`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup and pull request guidelines.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
