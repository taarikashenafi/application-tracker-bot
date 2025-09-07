#!/usr/bin/env python3
"""
Script to run the initial population of your Notion database with the last month's emails.
Run this once to populate your database, then the GitHub workflow will handle daily updates.
"""

import os
import sys
import subprocess

def main():
    print("🚀 Running initial population of Notion database...")
    print("This will scan the last 30 days of emails and populate your database.")
    print("After this, the GitHub workflow will handle daily updates automatically.")
    print()
    
    # Check if we're in a virtual environment
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  Warning: You're not in a virtual environment.")
        print("It's recommended to activate your virtual environment first:")
        print("  source venv/bin/activate")
        print()
    
    # Check if required environment variables are set
    required_vars = ["NOTION_TOKEN", "NOTION_DATABASE_ID", "IMAP_USER", "IMAP_PASS"]
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print()
        print("Please set these environment variables before running the script.")
        print("You can create a .env file with:")
        print("  NOTION_TOKEN=your_notion_token")
        print("  NOTION_DATABASE_ID=your_database_id")
        print("  IMAP_USER=your_email@gmail.com")
        print("  IMAP_PASS=your_app_password")
        return 1
    
    print("✅ All required environment variables are set.")
    print()
    
    # Run the bot in populate mode
    try:
        print("📧 Starting email processing...")
        result = subprocess.run([
            sys.executable, "bot.py", "--mode", "populate"
        ], check=True)
        
        print()
        print("🎉 Initial population completed successfully!")
        print("Your Notion database should now be populated with applications from the last 30 days.")
        print()
        print("Next steps:")
        print("1. Check your Notion database to verify the entries look correct")
        print("2. The GitHub workflow will now run daily to catch new applications")
        print("3. You can manually trigger the workflow anytime from the GitHub Actions tab")
        
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running the bot: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
