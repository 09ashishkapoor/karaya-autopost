# Generic Posting Refactor and Bluesky Publisher Design

## Goal

Convert the repo from a tweet-specific generator into a generic short-form posting tool, then add Bluesky as the first supported publisher.

This is a clean-break migration. Old tweet-specific names and paths will be removed rather than supported in parallel.

## Scope

In scope:

- Rename the generator, configs, schema fields, and generated output paths to generic post-oriented names
- Update docs, tests, helper scripts, and ignore rules to match the new naming
- Add a Bluesky publishing script that posts the next queued text record in strict order
- Add Bluesky state tracking for ordered posting
- Add a Bluesky GitHub Actions workflow using Bluesky credentials

Out of scope:

- Compatibility aliases for old `tweet_*` names
- Multi-platform posting abstraction in this pass
- Mastodon, Threads, Tumblr, or Nostr publishers
- Media/image posting
- Scheduling beyond the single GitHub Actions workflow

## Recommended Architecture

### 1. Generic content generation layer

Replace the current tweet-specific generator contract with a generic post contract:

- `generate_tweets.py` -> `generate_posts.py`
- `tweet_config.json` -> `post_config.json`
- `tweet_config_mahakali.json` -> `post_config_mahakali.json`
- `tweet_template_examples.md` -> `post_template_examples.md`

Config schema:

- `tweet_template` -> `post_template`
- `max_length` remains, because it is already generic enough

Generated record schema:

- `tweet_text` -> `post_text`
- `fits_twitter_limit` -> `fits_length_limit`

Output file names:

- `output/generated_tweets.csv` -> `output/generated_posts.csv`
- `output/generated_tweets.json` -> `output/generated_posts.json`
- `output/generated_tweets_mahakali.csv` -> `output/generated_posts_mahakali.csv`
- `output/generated_tweets_mahakali.json` -> `output/generated_posts_mahakali.json`

The record shape remains otherwise unchanged:

- `index`
- `name`
- `meaning`
- `post_text`
- `character_count`
- `fits_length_limit`
- `source_file`

### 2. Bluesky publishing layer

Add a new publisher script:

- `post_next_bluesky.py`

Responsibilities:

- Load the generic queue JSON
- Validate that each record has non-empty `post_text`
- Read Bluesky credentials from environment
- Authenticate with Bluesky using `com.atproto.server.createSession`
- Create a post using `com.atproto.repo.createRecord`
- Advance persistent state only after a successful post

Bluesky queue behavior stays intentionally simple:

- one account
- one queue file
- one text post per run
- first-to-last order
- no randomness
- no threads
- no images

### 3. Bluesky state tracking

State file:

- `output/bluesky_post_state.json`

State shape:

- `version`
- `source_json_path`
- `last_posted_index`
- `posted_record_uris`
- `posted_cids`
- `posted_timestamps`
- `posted_text_hashes`
- `history`

Each history item should store:

- `queue_index`
- `source_index`
- `post_uri`
- `cid`
- `posted_at`
- `text_hash`
- `post_text`

This keeps state auditable and platform-specific without pretending multiple platforms share one state format yet.

## Data Flow

### Generation flow

1. Load JSON config
2. Resolve relative paths from config directory
3. Parse source text entries
4. Render `post_text` using `post_template`
5. Mark `fits_length_limit` against `max_length`
6. Write CSV and JSON exports

### Bluesky posting flow

1. Load `output/generated_posts.json`
2. Load `output/bluesky_post_state.json`
3. Compute next queue position from `last_posted_index`
4. Stop cleanly if the queue is complete
5. Validate the selected record and ensure text is within Bluesky-safe limits configured by this repo
6. Authenticate against Bluesky
7. Submit the post record
8. Update state with URI, CID, timestamp, and hash
9. Save state

### GitHub Actions flow

1. Checkout repo
2. Set up Python
3. Run `python post_next_bluesky.py --json output/generated_posts.json --state output/bluesky_post_state.json`
4. Commit state file only if it changed

## Error Handling

### Generator

- Missing required config keys should raise `ValueError`
- Invalid source lines should be skipped and counted
- Relative path resolution should remain deterministic

### Bluesky publisher

- Missing credentials should raise a clear runtime error naming the missing variables
- Non-200 HTTP responses should be surfaced with response details
- Malformed queue or malformed state files should fail loudly
- Queue completion should exit cleanly without modifying state
- State must not advance when authentication or posting fails

## Testing Strategy

### Generator tests

Update existing generator tests to assert:

- new config keys (`post_template`)
- new record keys (`post_text`, `fits_length_limit`)
- renamed script/module imports
- CSV and JSON output still write successfully

### Bluesky publisher tests

Add tests for:

- default state creation
- UTF-8 BOM handling for state files
- next queue position logic
- successful post flow updates state
- queue completion path

Network calls should be mocked at the function boundary so tests remain offline and dependency-free.

## Implementation Order

1. Rename generator script and update imports/tests
2. Rename config keys and output schema
3. Rename config files and generated output paths
4. Update docs, batch script, and `.gitignore`
5. Add Bluesky publisher script and tests
6. Add Bluesky workflow and `.env.example` entries
7. Run test suite and final repo-wide search for stale tweet-specific references

## Tradeoffs

The clean break intentionally sacrifices backward compatibility to avoid carrying a fake abstraction layer. This is correct for a small repo because:

- the current integration has already been removed
- the repo has low migration surface area
- future platforms will be easier to add on generic names

The Bluesky publisher remains separate from the generator rather than introducing a plugin framework. That is deliberate YAGNI: one generic queue plus one concrete publisher is enough for the current goal.
