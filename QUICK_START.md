# 🚀 Quick Start - Catch Up on Missed Entries

## Will it cover all the entries I've missed? ✅ YES!

The bot will cover **all missed entries** when you run it with the appropriate lookback period.

## Easiest Way: Use GitHub Actions

### Step 1: Go to Your Repository
1. Open your GitHub repository in a browser
2. Click on the **"Actions"** tab

### Step 2: Run the Catch-Up Workflow
1. In the left sidebar, find **"notion-email-bot-catchup"**
2. Click on it
3. Click the **"Run workflow"** button (top right)
4. Click **"Run workflow"** again in the dropdown

### Step 3: Wait and Check Results
- The workflow will run and process emails from the last **90 days**
- You'll see a summary showing:
  - How many emails were found
  - How many were processed
  - How many entries were created/updated
- Check your Notion database to see the new entries!

## What the Catch-Up Does

✅ Searches through the last **90 days** of emails  
✅ Finds all application confirmation emails  
✅ Creates new entries in Notion (or updates existing ones)  
✅ Prevents duplicates  
✅ Shows detailed statistics  

## Alternative: Run Locally

If you want to run it locally (requires environment variables):

```bash
# Navigate to project directory
cd /path/to/application-tracker-bot

# Activate virtual environment (if using one)
source venv/bin/activate

# Install dependencies (if needed)
pip install notion-client python-dotenv

# Catch up on last 90 days
python bot.py --days 90
```

## Need a Different Time Period?

You can customize the lookback period:

```bash
# Last 60 days
python bot.py --days 60

# Last 120 days (4 months)
python bot.py --days 120

# Last 30 days
python bot.py --mode populate
```

## After Catching Up

The bot will continue running **automatically every day** at 9 AM UTC via GitHub Actions. No need to run it manually again unless you want to catch up on more missed entries.

## Troubleshooting

**Question: "How do I know if it worked?"**  
→ Check the workflow run output - it shows a summary with counts of processed/failed entries

**Question: "What if emails are older than 90 days?"**  
→ Increase the `--days` value (e.g., `--days 180` for 6 months)

**Question: "Some emails were skipped?"**  
→ Check the "PROCESSING SUMMARY" in the output - it explains why emails were skipped

**Question: "How do I check if entries were created?"**  
→ Look at your Notion database - new entries should appear there

## More Help

See [HOW_TO_RUN.md](HOW_TO_RUN.md) for detailed instructions and troubleshooting.

