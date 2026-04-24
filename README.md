# Karaya Autopost

Karaya Autopost is a small, dependency-free Python utility for turning devotional name-and-meaning text files into tweet-ready CSV and JSON exports.

It was built for simple devotional posting workflows: keep source entries in plain text, choose a tweet template in JSON, and generate structured exports that can be reviewed, scheduled, or imported elsewhere.

## Features

- Parses plain `name: meaning` source files.
- Accepts numbered source lists such as `1. Kali: The Black Goddess`.
- Renders tweet text from a configurable template.
- Exports matching CSV and JSON records.
- Flags records that exceed a configurable character limit.
- Posts one tweet at a time from JSON in strict queue order using the official X API.
- Supports hourly GitHub Actions autopost with persistent in-repo state.
- Uses only the Python standard library at runtime.

## Repository Contents

- `generate_tweets.py` - command-line generator and parsing/export helpers.
- `post_next_tweet.py` - posts exactly one next tweet from a generated JSON queue.
- `tweet_config.json` - Kalabhairava tweet export configuration.
- `tweet_config_mahakali.json` - Mahakali tweet export configuration.
- `.github/workflows/x-autopost.yml` - hourly GitHub Actions workflow.
- `output/post_state.json` - persistent posting state committed back to the repo.
- `combined_kalabhairava_onelinemeanings_nosalutations_FULL_APRIL22.txt` - Kalabhairava source entries.
- `combined_mahakali_onelinemeanings__FULL_APRIL22.txt` - Mahakali source entries.
- `requirements-dev.txt` - development-only test dependency list.
- `tests/test_generate_tweets.py` - pytest coverage for config loading, parsing, rendering, and file exports.

## Requirements

- Python 3.10 or newer.
- `pytest` only if you want to run the test suite.

The generator itself uses only the Python standard library.

## Quick Start

Run commands from the repository root:

```bash
python generate_tweets.py --config tweet_config.json
python generate_tweets.py --config tweet_config_mahakali.json
```

By default, these write files under `output/`:

- `output/generated_tweets.csv`
- `output/generated_tweets.json`
- `output/generated_tweets_mahakali.csv`
- `output/generated_tweets_mahakali.json`

The script prints the number of generated tweets, output paths, how many tweets exceed the configured length limit, and how many malformed source lines were skipped.

## GitHub Actions Autopost

This repo includes a production v1 autopost flow:

- queue source: `output/generated_tweets.json`
- state file: `output/post_state.json`
- schedule: hourly at minute `17`
- posting order: first to last, no randomness
- posting mode: one text post per run

### Required GitHub Repository Secrets

Add these in `Settings -> Secrets and variables -> Actions`:

- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

### Workflow Behavior

Workflow file: `.github/workflows/x-autopost.yml`

- Runs on cron `17 * * * *` and supports manual `workflow_dispatch`.
- Uses workflow concurrency group `x-autopost` to prevent overlapping posts.
- Calls:

```bash
python post_next_tweet.py --json output/generated_tweets.json --state output/post_state.json
```

- Commits `output/post_state.json` back to the repo only when state changes.

### State Semantics

`output/post_state.json` tracks:

- source queue path
- last posted queue index (1-based)
- posted tweet IDs
- posted timestamps
- tweet text hashes
- full posting history entries

State advances only after a successful API post.
If a run fails, state is not advanced.

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
  "tweet_template": "Today's name is {name}. {meaning} Jai Bhairava.",
  "csv_output": "output/generated_tweets.csv",
  "json_output": "output/generated_tweets.json",
  "max_length": 280
}
```

Required fields:

- `input_file` - source text file to parse.
- `tweet_template` - Python format string used to render each tweet.
- `csv_output` - CSV export path.
- `json_output` - JSON export path.

Optional fields:

- `max_length` - tweet length limit used for the `fits_twitter_limit` flag. Defaults to `280`.

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
- `tweet_text`
- `character_count`
- `fits_twitter_limit`
- `source_file`

## Run Tests

```bash
python -m pytest tests/test_generate_tweets.py -v
```

Current test coverage verifies path resolution, accepted input formats, malformed-line handling, tweet rendering, length-limit flags, and CSV/JSON file creation.

## Public Release Notes

- Generated exports are ignored by git; regenerate them locally as needed.
- The included devotional source files are part of the project data. Before publishing or redistributing modified datasets, confirm that any added content can be shared publicly.
- This project does not require API keys, tokens, or private service credentials.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup and pull request guidelines.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
