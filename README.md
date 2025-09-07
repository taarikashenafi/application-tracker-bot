# Notion Email Bot

Automatically tracks job applications by parsing email confirmations and updating a Notion database.

## Features

- ✅ Automatically detects job application confirmation emails
- ✅ Extracts company names, roles, application dates, and statuses
- ✅ Updates Notion database with application tracking
- ✅ Prevents duplicate entries
- ✅ Runs daily via GitHub Actions

## Setup

### 1. GitHub Secrets

Set these secrets in your GitHub repository:

- `NOTION_TOKEN`: Your Notion integration token
- `NOTION_DATABASE_ID`: Your Notion database ID
- `IMAP_USER`: Your email address
- `IMAP_PASS`: Your email app password (Gmail) or account password

### 2. Initial Population

1. Go to **Actions** tab in your GitHub repository
2. Run the `notion-email-bot-populate` workflow manually
3. This will scan the last 30 days and populate your database

### 3. Daily Operation

After initial population, the `notion-email-bot` workflow will run daily at 9 AM UTC to catch new applications.

## Usage

### Manual Runs

```bash
# Check last day's emails
python bot.py --mode daily

# Check last 30 days (initial population)
python bot.py --mode populate

# Check custom number of days
python bot.py --days 7
```

### Command Line Options

- `--mode {populate,daily}`: Set the operation mode
- `--days N`: Override number of days to check
- `--debug-schema`: Print database schema and exit

## Workflow Files

- `notion-email-bot.yml`: Daily workflow (runs automatically)
- `notion-email-bot-populate.yml`: Initial population (manual trigger only)

## Requirements

- Python 3.11+
- notion-client
- python-dotenv

## Database Schema

The bot expects a Notion database with these properties:

- **Company Name** (Title)
- **Role / Position** (Rich Text)
- **Application Date** (Date)
- **Application Status** (Status)
- **Application Link / Portal** (URL)
- **Location** (Rich Text)
- **Contact** (Rich Text)
- **Notes** (Rich Text)
