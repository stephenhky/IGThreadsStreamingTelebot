# IGThreadsStreamingTelebot

A Telegram bot webhook that collects Instagram and Threads links from chat messages and logs them to a Google Sheet. Designed to run on AWS Lambda behind API Gateway.

## Architecture

```
Telegram message → API Gateway → Lambda (this project) → Google Sheet
```

Each incoming link is stored as a row:

| timestamp | url | rectified url | username | platform | status | suffix | comments |
|-----------|-----|---------------|----------|----------|--------|--------|----------|
| 2026-08-19T04:17:00+00:00 | https://instagram.com/p/ABC123 | https://instagram.com/p/ABC123 | | instagram | PENDING | | |

New links are appended to the worksheet named by `GOOGLE_WORKSHEET_NAME` (default
`Links`) with a `PENDING` status.

## Commands

Send any of the following as a message to the bot:

| Command | Action |
|---------|--------|
| `/archive` | Move S3 spreadsheet folders into the S3 `archive/` prefix (see [S3](#s3)). |
| `/garchive` | Move every row labelled `DOWNLOADED` from the `stream` worksheet to the `archive` worksheet, then remove them from `stream`. |

`/garchive` operates on the tabs named by `GOOGLE_STREAM_WORKSHEET_NAME` and
`GOOGLE_ARCHIVE_WORKSHEET_NAME`. The `archive` worksheet is created on first use
(copied header from `stream`). Rows whose **status** column equals
`GOOGLE_DOWNLOADED_STATUS` (default `DOWNLOADED`) are the ones that get moved.

## Quick Start

```bash
# 1. Clone
git clone <repo-url>
cd IGThreadsStreamingTelebot

# 2. Install (editable)
pip install -e ".[dev]"

# 3. Run tests
pytest
```

## Configuration

Copy `.env.example` → `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather |
| `GOOGLE_SPREADSHEET_ID` | The ID from the Google Sheet URL |
| `GOOGLE_WORKSHEET_NAME` | Worksheet tab name (default: `Links`) |
| `GOOGLE_STREAM_WORKSHEET_NAME` | Tab for the active link stream – source for `/garchive` (default: `stream`) |
| `GOOGLE_ARCHIVE_WORKSHEET_NAME` | Tab where `/garchive` moves DOWNLOADED items (default: `archive`) |
| `GOOGLE_DOWNLOADED_STATUS` | Status label that marks items to archive (default: `DOWNLOADED`) |
| `GOOGLE_SA_KEY_FILE` | Path to service-account JSON key file |
| `GOOGLE_SA_KEY_JSON` | *Or* inline the JSON key (useful for Lambda) |

## Project Structure

```
src/ig_threads_telebot/
├── __init__.py
├── handler.py      # Lambda entry point
├── telegram.py     # Parse Telegram updates, extract IG/Threads links
├── sheets.py       # Google Sheets append + archive logic
└── s3.py           # S3 folder archiving
tests/
└── test_telegram.py
```

## Deployment

Deploy to AWS Lambda with API Gateway as the trigger. Set the Telegram webhook to your API Gateway endpoint:

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<API_GATEWAY_URL>"
```
