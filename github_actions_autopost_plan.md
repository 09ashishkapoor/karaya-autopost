# GitHub Actions Autopost Plan

## Goal

Run the X/Twitter autopost bot away from the local PC because the local machine uses a VPN with frequently rotating IPs.

The first production version should stay simple:

- one X account
- one specified generated JSON file
- one text post per hour
- posts in JSON order from first to last
- no randomness
- no images/media
- no dry run
- official X API only

## Recommendation

Use GitHub Actions for the first hosted version.

GitHub Actions is a good fit because:

- it avoids posting from a frequently rotating local VPN IP
- it can run hourly with a cron schedule
- it can store X API credentials in GitHub Actions secrets
- it should fit within GitHub's free limits for this workload
- it keeps deployment simple while the bot is still small

## Why Not Local PC First

The local PC is workable technically, but the rotating VPN IP adds unnecessary uncertainty.

The goal is not to bypass X enforcement. The goal is to use the official API from a normal, stable automation environment.

## GitHub Actions Free Limit Fit

An hourly workflow runs about:

```text
24 runs/day * 30 days = about 720 runs/month
```

If each job completes in under a minute, this should remain comfortably within typical GitHub Free private-repository Actions limits. Public repositories generally get free standard GitHub-hosted runner minutes.

Official references:

- GitHub Actions billing: https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions
- GitHub included usage: https://docs.github.com/en/billing/reference/product-usage-included

## Scheduling Caveat

GitHub scheduled workflows are not exact timers. They can be delayed or occasionally dropped during high load, especially at the start of the hour.

Use an offset minute instead of minute `0`:

```yaml
cron: "17 * * * *"
```

Official reference:

- Scheduled workflows: https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows

For this bot, occasional delay is acceptable. If one run is missed, the next run should post the next unposted tweet.

## Proposed Architecture

```text
GitHub Actions hourly cron
        |
        v
checkout repo
        |
        v
python post_next_tweet.py --json output/generated_tweets.json
        |
        v
post one text tweet through official X API
        |
        v
update output/post_state.json
        |
        v
commit state file back to repo
```

## State Handling

GitHub Actions runners are temporary. Each run starts fresh, so the bot needs persistent state.

Recommended v1 state:

```text
output/post_state.json
```

This file should track:

- source JSON path
- last posted index
- posted tweet IDs
- posted timestamps
- tweet text hash

Recommended v1 approach:

- update `output/post_state.json` after a successful X API post
- commit that state file back to the repo
- never advance state if the API post fails

This keeps the bot auditable and easy to recover.

## Concurrency

Use workflow concurrency so two scheduled runs cannot post at the same time:

```yaml
concurrency:
  group: x-autopost
  cancel-in-progress: false
```

## Repository Visibility

### Private Repo

Recommended if the content queue should stay private before posting.

Pros:

- source JSON and future posts stay private
- secrets stay protected
- hourly bot should fit within free private-repo minutes

Cons:

- consumes GitHub Actions included minutes

### Public Repo

Pros:

- standard GitHub-hosted runner minutes are generally free

Cons:

- generated tweet content and source files are public
- future scheduled content may be visible before it posts

## X/Twitter Risk Guidance

Use the official X API only.

Avoid:

- browser automation
- scraping
- proxy/IP rotation
- auto-liking
- auto-following
- auto-replying
- auto-DMs
- user mentions
- trending or unrelated hashtags
- repeated duplicate posts

Recommended:

- one relevant hashtag per post
- ordered devotional content
- transparent account bio
- automated account label if available
- simple text-only posting
- no engagement automation

Official references:

- X automation rules: https://help.x.com/en/rules-and-policies/x-automation
- X platform manipulation/spam policy: https://help.x.com/en/rules-and-policies/platform-manipulation
- X automated account labels: https://help.x.com/en/using-twitter/automated-account-labels
- X API post management: https://docs.x.com/x-api/posts/manage-tweets/introduction
- X API rate limits: https://docs.x.com/x-api/fundamentals/rate-limits

## Final Recommendation

Use GitHub Actions in a private repo, scheduled hourly at minute `17`, with one state file committed back to the repo after each successful post.

This is the simplest reliable setup for the current scope:

- one account
- one JSON queue
- one post per hour
- text only
- official API
- no local VPN dependency
