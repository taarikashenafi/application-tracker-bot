# How to Run the Notion Email Bot

## 🚀 Quick Start - Catch Up on Missed Entries

### Option 1: Using GitHub Actions (Easiest - Recommended)

To catch up on **all missed entries from the past 3 months**:

1. **Go to your GitHub repository**
   - Navigate to: `https://github.com/YOUR_USERNAME/YOUR_REPO`

2. **Click on the "Actions" tab**

3. **Find the "notion-email-bot" workflow**

4. **Click "Run workflow"** (button on the right)

5. **Modify the workflow file** to catch up on missed entries:
   - Click on `.github/workflows/notion-email-bot.yml` in your repo
   - Click "Edit" (pencil icon)
   - Change line 16 from:
     ```yaml
     - run: python bot.py --mode daily
     ```
     to:
     ```yaml
     - run: python bot.py --days 90
     ```
   - Commit the change
   - Go back to Actions and run the workflow again

   **OR** use the new catch-up workflow (see below)

### Option 2: Use the Catch-Up Workflow (Better)

I've created a dedicated catch-up workflow that looks back 90 days:

1. Go to **Actions** tab
2. Find **"notion-email-bot-catchup"** workflow
3. Click **"Run workflow"** → **"Run workflow"**
4. This will process the last 90 days of emails

### Option 3: Run Locally (If you have environment variables set)

```bash
# Navigate to the project directory
cd /path/to/application-tracker-bot

# Activate virtual environment (if using one)
source venv/bin/activate  # or: . venv/bin/activate

# Install dependencies (if needed)
pip install notion-client python-dotenv

# Catch up on last 90 days
python bot.py --days 90

# Or use populate mode (last 30 days)
python bot.py --mode populate

# Or check just the last 7 days
python bot.py --mode daily
```

## 📅 Will It Cover Missed Entries?

**Yes, but you need to specify how far back to look:**

| Mode | Days Back | Best For |
|------|-----------|----------|
| `--days 90` | 90 days | **Catching up on 3 months of missed entries** |
| `--days 60` | 60 days | Catching up on 2 months |
| `--days 30` | 30 days | Catching up on 1 month |
| `--mode populate` | 30 days | Initial database setup |
| `--mode daily` | 7 days | Regular daily runs |

**Recommendation**: Since you mentioned missing entries for "months", use:
```bash
python bot.py --days 90
```

This will:
- ✅ Search through the last 90 days of emails
- ✅ Process all application confirmation emails found
- ✅ Create/update entries in your Notion database
- ✅ Show detailed statistics of what was processed
- ✅ Skip duplicates (won't create duplicate entries)

## 🔄 Regular Daily Operation

After catching up, the bot will run **automatically every day at 9 AM UTC** via GitHub Actions.

The daily mode looks back **7 days** to catch any delayed emails.

## 📊 Understanding the Output

When the bot runs, you'll see:

```
INFO: Found 150 total emails in the last 90 days
...processing emails...
======================================================================
PROCESSING SUMMARY
======================================================================
Total emails found: 150
✅ Processed: 45
✅ Successfully upserted: 43
❌ Failed upserts: 2
⏭️  Skipped (not application confirmation): 80
⏭️  Skipped (non-job keywords): 15
⏭️  Skipped (no company extracted): 10
======================================================================
```

This tells you:
- How many emails were found
- How many were actually processed
- Why others were skipped

## 🔧 Troubleshooting

### "No emails found"
- Check that IMAP credentials are correct
- Verify emails exist in your inbox
- Try increasing the lookback period

### "All emails skipped"
- Emails might not match the application confirmation patterns
- Check the diagnostic workflow to see what's being filtered

### "Failed upserts"
- Check Notion database schema
- Verify status options match what the bot expects
- Run the diagnostic workflow for details

## 🩺 Running Diagnostics

To check if everything is set up correctly:

1. Go to **Actions** tab
2. Find **"diagnostic"** workflow
3. Click **"Run workflow"** → **"Run workflow"**
4. Review the output to see connection status, schema compatibility, etc.

## 📝 Environment Variables Required

The bot needs these environment variables (already set in GitHub Secrets):
- `NOTION_TOKEN` - Your Notion integration token
- `NOTION_DATABASE_ID` - Your Notion database ID
- `IMAP_USER` - Your email address
- `IMAP_PASS` - Your email app password (Gmail) or account password

## ✅ Next Steps

1. **Run the catch-up workflow** with `--days 90` to cover missed entries
2. **Check the output** to see how many entries were created/updated
3. **Review your Notion database** to verify entries were added
4. **The bot will continue running daily** automatically after that

