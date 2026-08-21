# IGThreadsStreamingTelebot

A Telegram bot webhook that collects Instagram and Threads links from chat messages and logs them to a Google Sheet. Designed to run on AWS Lambda behind API Gateway.

## Architecture

```
Telegram message → API Gateway → Lambda (this project) → Google Sheet
```

Each incoming link is stored as a row:

| timestamp | url | platform | status | comments |
|-----------|-----|----------|--------|----------|
| 2026-08-19T04:17:00+00:00 | https://instagram.com/p/ABC123 | instagram | PENDING | |

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
| `GOOGLE_SA_KEY_FILE` | Path to service-account JSON key file |
| `GOOGLE_SA_KEY_JSON` | *Or* inline the JSON key (useful for Lambda) |

## Project Structure

```
src/ig_threads_telebot/
├── __init__.py
├── handler.py      # Lambda entry point
├── telegram.py     # Parse Telegram updates, extract IG/Threads links
└── sheets.py       # Google Sheets append logic
tests/
└── test_telegram.py
```

## Deployment

Deploy to AWS Lambda with API Gateway as the trigger. Set the Telegram webhook to your API Gateway endpoint:

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<API_GATEWAY_URL>"
```
