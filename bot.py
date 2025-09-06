# bot.py
# pip install: notion-client python-dotenv
import os, imaplib, email, re, datetime
from email.header import decode_header, make_header
from notion_client import Client

NOTION_TOKEN         = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID   = os.environ["NOTION_DATABASE_ID"]
IMAP_HOST            = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_USER            = os.environ["IMAP_USER"]          # your full email
IMAP_PASS            = os.environ["IMAP_PASS"]          # app password (Gmail) or account password (IMAP)
IMAP_FOLDER          = os.environ.get("IMAP_FOLDER", "INBOX")
IMAP_SINCE_DAYS      = int(os.environ.get("IMAP_SINCE_DAYS", "30"))  # look back n days each run

notion = Client(auth=NOTION_TOKEN)

def debug_database_schema():
    """Debug function to print the database schema and status options"""
    try:
        db_info = notion.databases.retrieve(database_id=NOTION_DATABASE_ID)
        print("=== DATABASE SCHEMA ===")
        for prop_name, prop_config in db_info["properties"].items():
            print(f"Property: '{prop_name}'")
            print(f"  Type: {prop_config['type']}")
            if prop_config['type'] in ['select', 'status']:
                options = prop_config.get(prop_config['type'], {}).get('options', [])
                print(f"  Options: {[opt['name'] for opt in options]}")
            print()
        return db_info
    except Exception as e:
        print(f"Error retrieving database schema: {e}")
        return None

def get_valid_status_options():
    """Get the valid status options from the database"""
    try:
        db_info = notion.databases.retrieve(database_id=NOTION_DATABASE_ID)
        status_prop = None
        for prop_name, prop_config in db_info["properties"].items():
            if prop_name == "Application Status" and prop_config['type'] == 'status':
                status_prop = prop_config
                break
        
        if status_prop:
            options = status_prop.get('status', {}).get('options', [])
            return [opt['name'] for opt in options]
        return []
    except Exception as e:
        print(f"Error getting status options: {e}")
        return []

def validate_status(status):
    """Check if the status is valid and return a valid alternative if not"""
    valid_options = get_valid_status_options()
    if not valid_options:
        print("WARNING: Could not retrieve valid status options, using original status")
        return status
    
    if status in valid_options:
        return status
    
    print(f"WARNING: Status '{status}' not found in valid options: {valid_options}")
    # Try to find a close match
    status_lower = status.lower()
    for option in valid_options:
        if status_lower in option.lower() or option.lower() in status_lower:
            print(f"Using closest match: '{option}'")
            return option
    
    # Default to first available option
    print(f"Using default status: '{valid_options[0]}'")
    return valid_options[0]

# --- helpers ---
def get_text_from_message(msg):
    """Return best-effort plain text from an email.message.Message."""
    # Prefer text/plain
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    pass
        # fallback to first text/html
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(errors="ignore")
                    # very light html-to-text fallback
                    text = re.sub(r"<[^>]+>", " ", html)
                    text = re.sub(r"\s+", " ", text)
                    return text.strip()
                except Exception:
                    pass
    else:
        ctype = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
            if payload is None:
                return ""
            text = payload.decode(errors="ignore")
            if ctype == "text/html":
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text)
            return text
        except Exception:
            return ""
    return ""

# --- subject lines to status mapping ---
SUBJECT_RULES = [
    # Rejection patterns (check first to avoid false positives)
    (re.compile(r"not move forward|reject|regret|declined|unsuccessful|not selected|not chosen|not proceed", re.I), "Rejected"),
    
    # Offer patterns
    (re.compile(r"offer|congratulations.*offer|we.*pleased.*offer", re.I), "Offer Received"),
    
    # Interview patterns
    (re.compile(r"interview.*scheduled|phone screen|assessment.*scheduled|coding challenge.*scheduled|interview.*invite", re.I), "Interview Scheduled"),
    (re.compile(r"interview|phone screen|assessment|coding challenge|technical interview|behavioral interview", re.I), "Interview Scheduled"),
    
    # Application confirmation patterns
    (re.compile(r"thanks for applying|application received|we received your application|application.*submitted|application.*confirmed", re.I), "Applied"),
    
    # In progress patterns
    (re.compile(r"next steps|moving forward|under review|in review|being considered|application.*review", re.I), "In Progress"),
]

def parse_company_and_role(subject, body, sender=""):
    """Extract company and role with better accuracy"""
    company = None
    role = None
    
    # Clean up subject
    clean_subject = re.sub(r"^(re:|fwd?:|fw:)\s*", "", subject, flags=re.I).strip()
    clean_subject = re.sub(r"\s*\[.*?\]\s*$", "", clean_subject).strip()
    
    # Extract company from sender email domain first (most reliable)
    if sender:
        domain_match = re.search(r"@([^.]+)\.", sender.lower())
        if domain_match:
            domain = domain_match.group(1)
            # Skip generic domains
            if domain not in ["gmail", "yahoo", "hotmail", "outlook", "linkedin", "indeed", "glassdoor", "hubspot", "mailchimp"]:
                company = domain.title()
                # Handle common company name variations
                company = re.sub(r"noreply|no-reply|careers|jobs|hr|talent", "", company, flags=re.I).strip()
                if company:
                    company = company.title()
    
    # Look for company name in email body (more reliable than subject)
    if not company:
        company_patterns = [
            r"at\s+([A-Z][a-zA-Z\s&\.]+?)(?:\s|$|,|\.|!)",
            r"from\s+([A-Z][a-zA-Z\s&\.]+?)(?:\s|$|,|\.|!)",
            r"Company:\s*([^\n\r,]+)",
            r"Organization:\s*([^\n\r,]+)",
            r"([A-Z][a-zA-Z\s&\.]+?)\s+is\s+hiring",
            r"([A-Z][a-zA-Z\s&\.]+?)\s+team"
        ]
        
        for pattern in company_patterns:
            match = re.search(pattern, body, re.I)
            if match:
                potential_company = match.group(1).strip()
                # Filter out common false positives and clean up
                if (len(potential_company) > 2 and 
                    potential_company.lower() not in ["the", "a", "an", "and", "or", "but", "our", "your", "this", "that"] and
                    not re.search(r"^(great|good|wonderful|amazing)", potential_company, re.I)):
                    company = potential_company
                    break
    
    # Extract role from email body (more reliable than subject)
    role_patterns = [
        r"Position:\s*([^\n\r,]+)",
        r"Role:\s*([^\n\r,]+)",
        r"Job Title:\s*([^\n\r,]+)",
        r"for the\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|,|\.|!)",
        r"([A-Z][a-zA-Z\s]+?(?:Engineer|Developer|Analyst|Manager|Intern|Associate|Specialist|Coordinator|Assistant|Consultant|Designer|Scientist))",
        r"([A-Z][a-zA-Z\s]+?(?:Engineer|Developer|Analyst|Manager|Intern|Associate|Specialist|Coordinator|Assistant|Consultant|Designer|Scientist))\s+position"
    ]
    
    for pattern in role_patterns:
        match = re.search(pattern, body, re.I)
        if match:
            potential_role = match.group(1).strip()
            if len(potential_role) > 3 and len(potential_role) < 100:
                role = potential_role
                break
    
    # Fallback: try to extract from subject if it looks like a job title
    if not role and clean_subject:
        # Look for job title patterns in subject
        job_title_patterns = [
            r"([A-Z][a-zA-Z\s]+?(?:Engineer|Developer|Analyst|Manager|Intern|Associate|Specialist|Coordinator|Assistant|Consultant|Designer|Scientist))",
            r"([A-Z][a-zA-Z\s]+?(?:Engineer|Developer|Analyst|Manager|Intern|Associate|Specialist|Coordinator|Assistant|Consultant|Designer|Scientist))\s+at",
            r"at\s+([A-Z][a-zA-Z\s]+?(?:Engineer|Developer|Analyst|Manager|Intern|Associate|Specialist|Coordinator|Assistant|Consultant|Designer|Scientist))"
        ]
        
        for pattern in job_title_patterns:
            match = re.search(pattern, clean_subject, re.I)
            if match:
                potential_role = match.group(1).strip()
                if len(potential_role) > 3 and len(potential_role) < 100:
                    role = potential_role
                    break
    
    # Clean up extracted values
    if company:
        company = re.sub(r"\s+", " ", company).strip()
        # Remove common suffixes
        company = re.sub(r"\s+(inc|llc|ltd|corp|corporation|company)$", "", company, flags=re.I)
    
    if role:
        role = re.sub(r"\s+", " ", role).strip()
        # Remove common prefixes/suffixes
        role = re.sub(r"^(the|a|an)\s+", "", role, flags=re.I)
        role = re.sub(r"\s+(position|role|job)$", "", role, flags=re.I)
    
    return company, role

def extract_application_url(body, subject):
    """Extract the most relevant application URL from email content"""
    # Find all URLs in the content
    urls = re.findall(r"https?://[^\s<>\"']+", body + " " + subject)
    
    if not urls:
        return None
    
    # Prioritize URLs that look like job application portals
    job_indicators = [
        "careers", "jobs", "apply", "application", "hiring", "recruiting",
        "workday", "greenhouse", "lever", "bamboohr", "smartrecruiters",
        "taleo", "icims", "jobvite", "ats", "portal"
    ]
    
    # Score URLs based on job-related keywords
    scored_urls = []
    for url in urls:
        score = 0
        url_lower = url.lower()
        
        # Higher score for job-related domains/keywords
        for indicator in job_indicators:
            if indicator in url_lower:
                score += 10
        
        # Lower score for generic domains
        generic_domains = ["googleapis.com", "fonts.googleapis.com", "linkedin.com", "facebook.com", "twitter.com"]
        for domain in generic_domains:
            if domain in url_lower:
                score -= 20
        
        # Prefer shorter URLs (less likely to be tracking links)
        if len(url) < 100:
            score += 5
            
        scored_urls.append((score, url))
    
    # Sort by score (highest first) and return the best URL
    scored_urls.sort(key=lambda x: x[0], reverse=True)
    
    if scored_urls and scored_urls[0][0] > 0:
        return scored_urls[0][1]
    elif scored_urls:
        return scored_urls[0][1]  # Return first URL even if low score
    else:
        return None

def extract_application_date(msg, subject, body):
    """Extract the actual application date from email content"""
    # Try to find date patterns in the email body first
    date_patterns = [
        r"applied on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"application date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"submitted on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"submitted\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",  # General date pattern
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, body, re.I)
        if match:
            date_str = match.group(1)
            try:
                # Try different date formats
                for fmt in ["%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%y", "%m-%d-%y"]:
                    try:
                        parsed_date = datetime.datetime.strptime(date_str, fmt).date()
                        # Don't use future dates or very old dates
                        if datetime.date(2020, 1, 1) <= parsed_date <= datetime.date.today():
                            return parsed_date.isoformat()
                    except ValueError:
                        continue
            except:
                continue
    
    # Try to extract date from subject line
    subject_date_patterns = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})",
    ]
    
    for pattern in subject_date_patterns:
        match = re.search(pattern, subject, re.I)
        if match:
            date_str = match.group(1)
            try:
                # Try different date formats including month names
                for fmt in ["%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%y", "%m-%d-%y", "%d %b %Y", "%d %B %Y"]:
                    try:
                        parsed_date = datetime.datetime.strptime(date_str, fmt).date()
                        if datetime.date(2020, 1, 1) <= parsed_date <= datetime.date.today():
                            return parsed_date.isoformat()
                    except ValueError:
                        continue
            except:
                continue
    
    # For confirmation emails, use email date as it's likely close to application date
    if any(word in subject.lower() for word in ["thanks", "received", "application", "confirmation", "submitted"]):
        try:
            # Get email date
            email_date_str = msg.get("Date", "")
            if email_date_str:
                # Parse email date (format: "Thu, 5 Sep 2024 10:30:00 -0700")
                from email.utils import parsedate_to_datetime
                email_date = parsedate_to_datetime(email_date_str).date()
                return email_date.isoformat()
        except:
            pass
    
    return None

def derive_status(subject, body):
    for rx, status in SUBJECT_RULES:
        if rx.search(subject) or rx.search(body):
            return status
    return "Not Applied Yet"  # default if nothing matches

def find_existing(url=None, company=None, role=None):
    ors = []
    if url:
        ors.append({"property": "Application Link / Portal", "url": {"equals": url}})
    if company and role:
        ors.append({
            "and": [
                {"property": "Company Name", "title": {"equals": company}},
                {"property": "Role / Position", "rich_text": {"equals": role}},
            ]
        })
    if not ors: return None
    resp = notion.databases.query(database_id=NOTION_DATABASE_ID, filter={"or": ors} if len(ors) > 1 else ors[0])
    return resp["results"][0]["id"] if resp["results"] else None

def upsert(company, role, status, url=None, applied_on=None, location=None, notes=None):
    # Validate and potentially correct the status
    validated_status = validate_status(status)
    print(f"DEBUG: Original status: '{status}', Validated status: '{validated_status}'")
    
    props = {
        "Company Name": {"title": [{"text": {"content": company or "(unknown company)"}}]},
        "Role / Position": {"rich_text": [{"text": {"content": role or "(unknown role)"}}]},
        "Application Status": {"status": {"name": validated_status}},
    }
    if url:         props["Application Link / Portal"] = {"url": url}
    if applied_on:  props["Application Date"] = {"date": {"start": applied_on}}
    if location:    props["Location"] = {"rich_text": [{"text": {"content": location}}]}
    if notes:       props["Notes"] = {"rich_text": [{"text": {"content": notes[:1900]}}]}

    page_id = find_existing(url=url, company=company, role=role)
    try:
        if page_id:
            notion.pages.update(page_id=page_id, properties=props)
            return "updated"
        else:
            notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
            return "created"
    except Exception as e:
        print(f"ERROR: Failed to upsert {company=} {role=} {status=}")
        print(f"Error details: {e}")
        # Try with a fallback status if the original status failed
        if "status" in str(e).lower():
            fallback_status = validate_status("Applied")
            print(f"Attempting fallback with status '{fallback_status}'...")
            props["Application Status"] = {"status": {"name": fallback_status}}
            try:
                if page_id:
                    notion.pages.update(page_id=page_id, properties=props)
                    return "updated (fallback)"
                else:
                    notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
                    return "created (fallback)"
            except Exception as e2:
                print(f"Fallback also failed: {e2}")
                return "failed"
        return "failed"

def fetch_recent_emails():
    print("DEBUG: IMAP_USER present?", bool(os.environ.get("IMAP_USER")))
    print("DEBUG: IMAP_PASS length:", len(os.environ.get("IMAP_PASS", "")))
    since_date = (datetime.date.today() - datetime.timedelta(days=IMAP_SINCE_DAYS)).strftime("%d-%b-%Y")
    M = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        M.login(IMAP_USER, IMAP_PASS)
    except imaplib.IMAP4.error as e:
        print("ERROR: IMAP authentication failed.")
        print("HINT: Ensure IMAP is enabled in Gmail, IMAP_USER matches the account that created the App Password, and IMAP_PASS is the 16-char app password with no spaces.")
        raise
    M.select(IMAP_FOLDER)
    # narrow subjects you care about; edit as you like:
    search_query = f'(SINCE {since_date})'
    typ, data = M.search(None, search_query)
    ids = data[0].split() if data and data[0] else []
    for eid in ids:
        typ, msg_data = M.fetch(eid, "(RFC822)")
        if typ != "OK": continue
        msg = email.message_from_bytes(msg_data[0][1])
        subject = str(make_header(decode_header(msg.get("Subject") or "")))
        # Filter out non-job application emails
        sender = msg.get("From", "").lower()
        subject_lower = subject.lower()
        
        # Skip LinkedIn emails and other non-job emails
        if any(skip_word in sender or skip_word in subject_lower for skip_word in [
            "linkedin", "noreply", "no-reply", "notifications", "marketing", 
            "newsletter", "promotional", "unsubscribe", "social media", "hubspot",
            "mailchimp", "constant contact", "salesforce", "zendesk"
        ]):
            continue
        
        # Skip emails that are clearly not job applications
        if any(skip_phrase in subject_lower for skip_phrase in [
            "this is your sign", "great news", "congratulations", "deadline", "reminder",
            "don't miss", "last chance", "expires", "closing soon", "apply now",
            "open positions", "we're hiring", "join our team"
        ]):
            continue
            
        # Only consider likely application emails:
        if not re.search(r"apply|application|interview|assessment|offer|declin|reject|next steps|thanks|position|role|job|candidate|confirmation|submitted", subject, re.I):
            continue

        body = get_text_from_message(msg)

        status = derive_status(subject, body)
        company, role = parse_company_and_role(subject, body, sender)

        # Skip if we couldn't extract a meaningful company name
        if not company or company.lower() in ["unknown", "unknown company", "our", "your", "this", "that", "the"]:
            print(f"SKIPPED: No meaningful company name extracted")
            print(f"  Subject: {subject[:100]}...")
            print(f"  Sender: {sender}")
            print("---")
            continue

        # Extract application URL - prioritize job-related URLs
        url = extract_application_url(body, subject)
        
        # Extract actual application date
        applied_on = extract_application_date(msg, subject, body)
        if not applied_on and status in ("Applied", "Not Applied Yet"):
            applied_on = datetime.date.today().isoformat()
            
        result = upsert(company, role, status, url=url, applied_on=applied_on, notes=subject)
        print(f"{result}: {company=} {role=} {status=} {url=} {applied_on=}")
        print(f"  Subject: {subject[:100]}...")
        print(f"  Sender: {sender}")
        print("---")
    M.logout()

if __name__ == "__main__":
    debug_database_schema()
    fetch_recent_emails()