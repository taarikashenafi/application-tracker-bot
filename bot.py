# bot.py
# pip install: notion-client python-dotenv
import os, imaplib, email, re, datetime, argparse
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

# Debug: Check notion-client version and available methods
try:
    import notion_client
    print(f"DEBUG: notion-client version: {notion_client.__version__}")
    print(f"DEBUG: Available databases methods: {[m for m in dir(notion.databases) if not m.startswith('_')]}")
except Exception as e:
    print(f"DEBUG: Could not check notion-client version: {e}")

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
        if not db_info or "properties" not in db_info:
            print(f"Warning: Database info missing 'properties' key. Keys: {list(db_info.keys()) if db_info else 'None'}")
            return []
        
        status_prop = None
        for prop_name, prop_config in db_info.get("properties", {}).items():
            if prop_name == "Application Status" and prop_config.get('type') == 'status':
                status_prop = prop_config
                break
        
        if status_prop:
            # Handle different possible structures
            if 'status' in status_prop:
                options = status_prop.get('status', {}).get('options', [])
            elif 'options' in status_prop:
                options = status_prop.get('options', [])
            else:
                print(f"Warning: Status property structure unexpected: {list(status_prop.keys())}")
                return []
            
            return [opt.get('name') for opt in options if isinstance(opt, dict) and 'name' in opt]
        return []
    except Exception as e:
        print(f"Error getting status options: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
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
# NOTE: gaps between key words are bounded (".{0,N}") rather than unbounded (".*").
# HTML-only emails get flattened to one long single-line string by get_text_from_message,
# so an unbounded ".*" can span completely unrelated sentences anywhere in the email and
# produce false-positive matches. Bounding the gap keeps matches scoped to one phrase.
SUBJECT_RULES = [
    # Rejection patterns (check first to avoid false positives)
    (re.compile(r"not move forward|reject|regret|declined|unsuccessful|not selected|not chosen|not proceed", re.I), "Rejected"),
    
    # Offer patterns
    (re.compile(r"offer|congratulations.{0,30}offer|we.{0,20}pleased.{0,20}offer", re.I), "Offer Received"),
    
    # Interview patterns
    (re.compile(r"interview.{0,20}scheduled|phone screen|assessment.{0,20}scheduled|coding challenge.{0,20}scheduled|interview.{0,20}invite", re.I), "Interview Scheduled"),
    (re.compile(r"interview|phone screen|assessment|coding challenge|technical interview|behavioral interview", re.I), "Interview Scheduled"),
    
    # Application confirmation patterns (most common for job application emails)
    (re.compile(r"we.{0,20}received.{0,20}your.{0,20}application|thank.{0,10}you.{0,10}for.{0,10}your.{0,10}application|application.{0,10}received|we.{0,20}received.{0,20}your.{0,20}job.{0,10}application|thank.{0,10}you.{0,10}for.{0,10}your.{0,10}online.{0,10}submission|we.{0,20}received.{0,20}your.{0,20}submission|application.{0,10}submitted|your.{0,10}application.{0,10}has.{0,10}been.{0,10}received", re.I), "Applied"),
    
    # In progress patterns
    (re.compile(r"next steps|moving forward|under review|in review|being considered|application.{0,20}review", re.I), "In Progress"),
]

# Emails that mention "application" incidentally but are not actual application-confirmation
# emails (newsletters, info sessions, marketing) - if any of these appear, skip regardless of
# an otherwise-matching confirmation pattern.
NON_APPLICATION_MARKERS = re.compile(
    r"info session|information session|webinar|newsletter|hiring event|career fair|"
    r"upcoming event|save the date|register now|join us for|office hours|"
    r"explore opportunities|update your profile|check out our|learn more about our program|"
    r"unsubscribe from these emails|browse jobs|new jobs? matching|job alert|"
    r"recommended jobs?|jobs? you may be interested|event confirmation|"
    r"you.{0,10}re registered|registration confirmed|rsvp confirmed|resume workshop|"
    r"career workshop|meetup-join|teams\.microsoft\.com",
    re.I,
)

# ATS / mailer domains that are never the actual employer - company name must come from the
# email body or sender display name instead of the sending domain in these cases.
ATS_OR_MAILER_DOMAINS = {
    "gmail", "yahoo", "hotmail", "outlook", "linkedin", "indeed", "glassdoor",
    "hubspot", "mailchimp", "myworkday", "workday", "ashbyhq", "ashby",
    "greenhouse", "lever", "icims", "smartrecruiters", "jobvite", "taleo",
    "bamboohr", "breezy", "jazzhr", "recruiterbox", "applytojob", "workable",
    "successfactors", "sendgrid", "mailgun", "amazonses", "sparkpostmail",
    "sparkpost", "notifications", "mail",
}

# Generic sender-display-name / extracted-company terms that are never a real company name.
GENERIC_NAME_TERMS = {
    "recruiting", "recruitment", "talent acquisition", "talent", "hr",
    "human resources", "careers", "career", "hiring team", "hiring",
    "no reply", "noreply", "do not reply", "team", "notifications",
    "the", "a", "an", "and", "or", "but", "our", "your", "this", "that",
    "warm", "hello", "recruiter",
}

# Words that indicate a plausible job title, used to validate extracted roles.
ROLE_KEYWORDS = (
    "engineer", "developer", "analyst", "manager", "intern", "associate",
    "specialist", "coordinator", "assistant", "consultant", "designer",
    "scientist", "program", "architect", "administrator", "representative",
    "technician", "researcher", "fellow", "officer", "executive", "lead",
    "product", "marketing", "sales", "finance", "operations", "support",
    "qa", "quality assurance", "software", "data", "engineering",
)

def _clean_company_candidate(name):
    """Validate/normalize a candidate company name; return None if it isn't usable."""
    if not name:
        return None
    name = re.sub(r"\s+", " ", name).strip(" \t\"'.,-")
    if not name or "@" in name or len(name) < 2 or len(name) > 60:
        return None
    if name.lower() in GENERIC_NAME_TERMS:
        return None
    # Reject anything that still looks like a raw email header/address fragment
    if re.search(r"<.*>", name) or re.search(r"\d{4,}", name):
        return None
    name = re.sub(r"\s+(inc|llc|ltd|corp|corporation|company|& co\.?)$", "", name, flags=re.I)
    return name.strip() or None


def _clean_role_candidate(role):
    """Validate/normalize a candidate role/title; return None if it doesn't look like a title."""
    if not role:
        return None
    role = re.sub(r"\s+", " ", role).strip(" \t\"'.,-")
    role = re.sub(r"^(the|a|an)\s+", "", role, flags=re.I)
    role = re.sub(r"\s+(position|role|job|opening|opportunity)$", "", role, flags=re.I)
    if not role or len(role) < 3 or len(role) > 80:
        return None
    if "@" in role or "http" in role.lower():
        return None
    if not any(kw in role.lower() for kw in ROLE_KEYWORDS):
        return None
    return role


def parse_company_and_role(subject, body, sender=""):
    """Extract company and role from job application confirmation emails.

    Company is resolved in priority order: explicit body phrasing (most reliable,
    since it names the employer directly) > sender display name > sending domain
    (skipped entirely for known ATS/mailer domains, since those never reflect the
    actual employer). Every candidate is validated before use so we never fall
    back to noise like a raw email address or a recruiter-team label.
    """
    company = None
    role = None

    clean_subject = re.sub(r"^(re:|fwd?:|fw:)\s*", "", subject, flags=re.I).strip()
    clean_subject = re.sub(r"\s*\[.*?\]\s*$", "", clean_subject).strip()

    company_mappings = {
        "hewlett": "Hewlett-Packard Enterprise", "hpe": "Hewlett-Packard Enterprise",
        "hp": "Hewlett-Packard Enterprise", "jpmorgan": "JPMorgan Chase & Co.",
        "chase": "JPMorgan Chase & Co.", "salesforce": "Salesforce", "google": "Google",
        "microsoft": "Microsoft", "amazon": "Amazon", "meta": "Meta", "facebook": "Meta",
        "apple": "Apple", "netflix": "Netflix", "uber": "Uber", "airbnb": "Airbnb",
        "spotify": "Spotify", "twitter": "Twitter", "linkedin": "LinkedIn", "adobe": "Adobe",
        "oracle": "Oracle", "ibm": "IBM", "intel": "Intel", "nvidia": "NVIDIA",
        "tesla": "Tesla", "spacex": "SpaceX", "openai": "OpenAI", "anthropic": "Anthropic",
        "stripe": "Stripe", "square": "Square", "paypal": "PayPal", "visa": "Visa",
        "mastercard": "Mastercard", "goldman": "Goldman Sachs", "morgan": "Morgan Stanley",
        "wells": "Wells Fargo", "bankofamerica": "Bank of America", "citi": "Citigroup",
        "pepsi": "PepsiCo", "coca": "Coca-Cola", "nike": "Nike", "adidas": "Adidas",
        "starbucks": "Starbucks", "mcdonalds": "McDonald's", "walmart": "Walmart",
        "target": "Target", "costco": "Costco", "lowes": "Lowe's", "dell": "Dell",
        "cisco": "Cisco", "vmware": "VMware", "redhat": "Red Hat", "dropbox": "Dropbox",
        "box": "Box", "slack": "Slack", "zoom": "Zoom", "figma": "Figma", "canva": "Canva",
        "notion": "Notion", "atlassian": "Atlassian", "trello": "Trello", "asana": "Asana",
        "monday": "Monday.com", "airtable": "Airtable", "zapier": "Zapier",
        "hubspot": "HubSpot", "pipedrive": "Pipedrive", "zendesk": "Zendesk",
        "freshworks": "Freshworks", "servicenow": "ServiceNow", "rivian": "Rivian",
        "citadel": "Citadel", "twitch": "Twitch", "disney": "Disney", "pinterest": "Pinterest",
        "coinbase": "Coinbase", "robinhood": "Robinhood", "waymo": "Waymo",
    }

    def apply_mapping(text):
        text_lower = text.lower()
        for key, full_name in company_mappings.items():
            if key in text_lower:
                return full_name
        return None

    # Priority 1: explicit "applying to/at <Company>" style phrasing in the body - this
    # names the actual employer directly and is more reliable than the sending domain,
    # which is frequently an ATS (Greenhouse, Ashby, Workday, etc.) rather than the employer.
    body_company_patterns = [
        r"appl(?:y|ying|ication)\s+(?:to|at|with)\s+([A-Z][\w&.\- ]{1,40}?)(?:\s*[.,!\n]|\s+for\s|\s+is\s|\s+has\s|$)",
        r"interest in\s+([A-Z][\w&.\- ]{1,40}?)(?:\s*[.,!\n]|$)",
        r"joining\s+([A-Z][\w&.\- ]{1,40}?)(?:\s*[.,!\n]|$)",
        r"(?:the|our)\s+([A-Z][\w&.\- ]{1,40}?)\s+(?:recruiting|talent acquisition|hiring)\s+team",
    ]
    for pattern in body_company_patterns:
        match = re.search(pattern, body, re.I)
        if match:
            candidate = _clean_company_candidate(match.group(1))
            if candidate:
                mapped = apply_mapping(candidate)
                company = mapped or candidate
                break

    # Priority 2: sender display name, e.g. '"Rivian Careers" <no-reply@rivian.com>'
    if not company and sender:
        display_match = re.match(r'\s*"?([^"<]+?)"?\s*<', sender)
        if display_match:
            display_name = display_match.group(1)
            # Strip generic recruiting-team suffixes to isolate the company name
            display_name = re.sub(
                r"\b(recruiting|recruitment|talent acquisition|talent|careers?|hiring team|"
                r"hiring|human resources|hr team|hr|no.?reply|do not reply|team|notifications)\b",
                "", display_name, flags=re.I,
            ).strip(" -|,")
            candidate = _clean_company_candidate(display_name)
            if candidate:
                mapped = apply_mapping(candidate)
                company = mapped or candidate

    # Priority 3: sending domain, but only if it's not a known ATS/mailer domain (those
    # send on behalf of many different employers, so the domain itself is not the company).
    if not company and sender:
        domain_match = re.search(r"@([^.]+)\.", sender.lower())
        if domain_match:
            domain = domain_match.group(1)
            if domain not in ATS_OR_MAILER_DOMAINS:
                mapped = apply_mapping(domain)
                if mapped:
                    company = mapped
                else:
                    candidate = _clean_company_candidate(domain.title())
                    if candidate:
                        company = candidate

    # --- Role extraction ---
    specific_role_patterns = [
        r"for the\s+([A-Za-z0-9][\w/&,.\- ]{2,60}?)\s+(?:position|role|opening|opportunity|req|internship)",
        r"application for\s+(?:the\s+)?([A-Za-z0-9][\w/&,.\- ]{2,60}?)(?:\s+(?:position|role|at|opening)|[.,!\n]|$)",
        r"appl(?:y|ying|ication)\s+for\s+(?:the\s+)?([A-Za-z0-9][\w/&,.\- ]{2,60}?)(?:\s+(?:position|role|at|opening)|[.,!\n]|$)",
        r"role of\s+([A-Za-z0-9][\w/&,.\- ]{2,60}?)(?:[.,!\n]|$)",
        r"Position:\s*([^\n\r,]{2,80})",
        r"Role:\s*([^\n\r,]{2,80})",
        r"Job Title:\s*([^\n\r,]{2,80})",
    ]
    # Generic fallback: a capitalized phrase ending in a job-title keyword. Word count is
    # capped (at most 4 words before the keyword) so this can't run away across an entire
    # HTML-flattened sentence the way an unbounded match would.
    generic_role_pattern = (
        r"\b([A-Z][\w&.\-]*(?:\s+[A-Za-z0-9&.\-]+){0,4}?\s+(?:Engineer|Developer|Analyst|Manager|"
        r"Intern(?:ship)?|Associate|Specialist|Coordinator|Assistant|Consultant|Designer|Scientist|"
        r"Architect|Representative|Technician|Researcher))\b"
    )

    # Try the specific, trigger-phrase patterns first (across subject, then body) - these
    # anchor to explicit phrasing like "application for the X position" and are far less
    # likely to accidentally swallow leading, unrelated words than the generic fallback.
    for source in (clean_subject, body):
        for pattern in specific_role_patterns:
            match = re.search(pattern, source, re.I)
            if match:
                candidate = _clean_role_candidate(match.group(1))
                if candidate:
                    role = candidate
                    break
        if role:
            break

    # Only fall back to the generic bare-keyword pattern if nothing more specific matched.
    if not role:
        for source in (clean_subject, body):
            match = re.search(generic_role_pattern, source)
            if match:
                candidate = _clean_role_candidate(match.group(1))
                if candidate:
                    role = candidate
                    break

    return company, role


def extract_application_url(body, subject):
    """Extract the URL most likely to be the original job posting/application page."""
    urls = re.findall(r"https?://[^\s<>\"')\]]+", body + " " + subject)

    if not urls:
        return None

    # Strong signal: URL path shape used by job-detail pages on common ATS platforms
    # (e.g. greenhouse.io/.../jobs/12345, boards.greenhouse.io/company/jobs/12345,
    # myworkdayjobs.com/.../job/..., lever.co/company/<uuid>, ashbyhq.com/.../<slug>).
    job_posting_path_re = re.compile(
        r"/(jobs?|careers?|postings?|positions?|opening|req(?:uisition)?s?)/[\w\-./]+", re.I
    )

    # General job-related keywords anywhere in the URL (weaker signal on their own).
    job_indicators = [
        "careers", "jobs", "apply", "application", "hiring", "recruiting",
        "workday", "greenhouse", "lever", "bamboohr", "smartrecruiters",
        "taleo", "icims", "jobvite", "ashbyhq", "workable", "portal", "posting",
    ]

    # Links that are never the job posting itself - tracking pixels, unsubscribe,
    # help/privacy pages, and generic social/marketing domains.
    exclude_markers = [
        "unsubscribe", "optout", "opt-out", "privacy", "helpcenter", "support.",
        "facebook.com", "twitter.com", "x.com", "instagram.com", "tiktok.com",
        "googleapis.com", "gstatic.com", "fonts.", "mailtrack", "sendgrid.net/wf/open",
        "click.", "track.", "pixel.",
    ]

    scored_urls = []
    for url in urls:
        url_lower = url.lower()
        if any(marker in url_lower for marker in exclude_markers):
            continue

        score = 0
        if job_posting_path_re.search(url):
            score += 25
        for indicator in job_indicators:
            if indicator in url_lower:
                score += 8
        if len(url) < 150:
            score += 5
        if "linkedin.com" in url_lower:
            score -= 15  # usually a generic company page, not the posting itself

        scored_urls.append((score, url))

    if not scored_urls:
        return None

    scored_urls.sort(key=lambda x: x[0], reverse=True)
    best_score, best_url = scored_urls[0]
    return best_url if best_score > 0 else None

def extract_application_date(msg, subject, body):
    """Extract the actual application date from email content"""
    # Try to find date patterns in the email body first
    date_patterns = [
        r"applied on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"application date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"submitted on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"submitted\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"received on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"received\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
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
                # For application confirmations, the email date is usually the same day or next day
                # So we can use it as the application date
                return email_date.isoformat()
        except:
            pass
    
    return None

def derive_status(subject, body):
    for rx, status in SUBJECT_RULES:
        if rx.search(subject) or rx.search(body):
            return status
    return "Not Applied Yet"  # default if nothing matches

def find_existing(url=None, company=None, role=None, applied_on=None):
    """Find existing entry by URL, or by company+date combination"""
    ors = []
    
    # First priority: exact URL match
    if url:
        ors.append({"property": "Application Link / Portal", "url": {"equals": url}})
    
    # Second priority: company + date combination (most reliable for preventing duplicates)
    if company and applied_on:
        ors.append({
            "and": [
                {"property": "Company Name", "title": {"equals": company}},
                {"property": "Application Date", "date": {"equals": applied_on}}
            ]
        })
    
    # Third priority: company + role (only if role is meaningful)
    if company and role and role not in ["(unknown role)", "(role unclear)", "unknown role", "role", "position"]:
        ors.append({
            "and": [
                {"property": "Company Name", "title": {"equals": company}},
                {"property": "Role / Position", "rich_text": {"equals": role}},
            ]
        })
    
    # Fourth priority: just company name (fallback, but less reliable)
    if company and not ors:
        ors.append({"property": "Company Name", "title": {"equals": company}})
    
    if not ors: 
        return None
    
    try:
        # Build the filter - use "or" if multiple conditions, otherwise use the single condition
        if len(ors) > 1:
            filter_obj = {"or": ors}
        else:
            filter_obj = ors[0]
        
        # Check if query method exists (for compatibility with different versions)
        if not hasattr(notion.databases, 'query'):
            print("Warning: databases.query() method not available in this version of notion-client")
            print("Attempting to use alternative approach...")
            # Fallback: return None to skip duplicate checking
            # This means duplicates might be created, but the bot will still work
            return None
        
        # Query the database
        resp = notion.databases.query(database_id=NOTION_DATABASE_ID, filter=filter_obj)
        
        if resp and "results" in resp and resp["results"]:
            return resp["results"][0]["id"]
        return None
    except AttributeError as e:
        # Fallback: try alternative API if query doesn't exist
        print(f"Warning: databases.query() not available: {e}")
        print("Skipping duplicate check - entries may be created even if duplicates exist")
        return None
    except Exception as e:
        print(f"Error querying database for existing entry: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        # Don't fail completely - just skip duplicate checking
        return None

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

    page_id = find_existing(url=url, company=company, role=role, applied_on=applied_on)
    print(f"DEBUG: Looking for existing entry with company='{company}', role='{role}', applied_on='{applied_on}', url='{url}'")
    print(f"DEBUG: Found existing page_id: {page_id}")
    
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

def fetch_recent_emails(days_back=None):
    """
    Fetch and process recent emails for job applications
    
    Args:
        days_back (int): Number of days to look back. If None, uses IMAP_SINCE_DAYS from environment
    """
    if days_back is None:
        days_back = IMAP_SINCE_DAYS
    
    print(f"DEBUG: IMAP_USER present?", bool(os.environ.get("IMAP_USER")))
    print(f"DEBUG: IMAP_PASS length:", len(os.environ.get("IMAP_PASS", "")))
    print(f"DEBUG: Looking back {days_back} days for emails")
    
    since_date = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%d-%b-%Y")
    print(f"DEBUG: Searching for emails since {since_date}")
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
    
    print(f"INFO: Found {len(ids)} total emails in the last {days_back} days")
    
    # Statistics tracking
    stats = {
        "total_emails": len(ids),
        "processed": 0,
        "skipped_not_confirmation": 0,
        "skipped_non_job_keywords": 0,
        "skipped_no_company": 0,
        "successful_upserts": 0,
        "failed_upserts": 0
    }
    
    for eid in ids:
        typ, msg_data = M.fetch(eid, "(RFC822)")
        if typ != "OK": continue
        msg = email.message_from_bytes(msg_data[0][1])
        subject = str(make_header(decode_header(msg.get("Subject") or "")))
        # Filter out non-job application emails
        sender = msg.get("From", "").lower()
        subject_lower = subject.lower()
        
        # ONLY process emails that are clearly job application confirmations.
        # Uses the module-level bounded-gap patterns (".{0,N}" instead of ".*") since an
        # unbounded ".*" can span an entire HTML-flattened, single-line email body and
        # false-positive-match on unrelated sentences (e.g. newsletters, info sessions).
        application_confirmations = [rx for rx, sts in SUBJECT_RULES if sts == "Applied"]

        body = get_text_from_message(msg)

        # Check if this is an application confirmation email
        is_application_email = any(
            pattern.search(subject) or pattern.search(body)
            for pattern in application_confirmations
        )

        # Skip if it's not an application confirmation
        if not is_application_email:
            stats["skipped_not_confirmation"] += 1
            continue

        # Skip informational/marketing emails that merely mention "application" in
        # passing (info sessions, newsletters, job-alert digests, etc.)
        if NON_APPLICATION_MARKERS.search(subject) or NON_APPLICATION_MARKERS.search(body):
            stats["skipped_non_job_keywords"] += 1
            continue

        # Additional filtering - skip if it contains non-job keywords
        if any(skip_word in sender.lower() or skip_word in subject_lower for skip_word in [
            "linkedin", "property", "rent", "payment", "maintenance", "verification", 
            "security", "deadline", "reminder", "notification", "social", "reacted",
            "externship", "admissions", "course", "class", "petscreening"
        ]):
            stats["skipped_non_job_keywords"] += 1
            continue

        status = derive_status(subject, body)
        company, role = parse_company_and_role(subject, body, sender)

        # Skip if we couldn't extract a validated, meaningful company name
        # (parse_company_and_role already validates candidates, so a None here means
        # nothing trustworthy was found rather than a name that merely looks generic)
        if not company:
            stats["skipped_no_company"] += 1
            print(f"SKIPPED: No meaningful company name extracted")
            print(f"  Subject: {subject[:100]}...")
            print(f"  Sender: {sender}")
            print("---")
            continue

        if not role:
            role = "(role unclear)"

        stats["processed"] += 1

        # Extract application URL - prioritize job-related URLs
        url = extract_application_url(body, subject)
        
        # Extract actual application date
        applied_on = extract_application_date(msg, subject, body)
        if not applied_on and status in ("Applied", "Not Applied Yet"):
            # For application confirmations, use email date as it's likely close to application date
            try:
                email_date_str = msg.get("Date", "")
                if email_date_str:
                    from email.utils import parsedate_to_datetime
                    email_date = parsedate_to_datetime(email_date_str).date()
                    # Don't use future dates
                    if email_date <= datetime.date.today():
                        applied_on = email_date.isoformat()
                    else:
                        applied_on = datetime.date.today().isoformat()
                else:
                    applied_on = datetime.date.today().isoformat()
            except:
                applied_on = datetime.date.today().isoformat()
            
        result = upsert(company, role, status, url=url, applied_on=applied_on, notes=subject)
        if "failed" in result:
            stats["failed_upserts"] += 1
        else:
            stats["successful_upserts"] += 1
        print(f"{result}: {company=} {role=} {status=} {url=} {applied_on=}")
        print(f"  Subject: {subject[:100]}...")
        print(f"  Sender: {sender}")
        print("---")
    
    # Print statistics summary
    print("\n" + "="*70)
    print("PROCESSING SUMMARY")
    print("="*70)
    print(f"Total emails found: {stats['total_emails']}")
    print(f"✅ Processed: {stats['processed']}")
    print(f"✅ Successfully upserted: {stats['successful_upserts']}")
    print(f"❌ Failed upserts: {stats['failed_upserts']}")
    print(f"⏭️  Skipped (not application confirmation): {stats['skipped_not_confirmation']}")
    print(f"⏭️  Skipped (non-job keywords): {stats['skipped_non_job_keywords']}")
    print(f"⏭️  Skipped (no company extracted): {stats['skipped_no_company']}")
    print("="*70 + "\n")
    
    M.logout()

def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description="Notion Email Bot for tracking job applications")
    parser.add_argument(
        "--mode", 
        choices=["populate", "daily"], 
        default="daily",
        help="Mode to run the bot in: 'populate' for initial database setup (30 days), 'daily' for regular runs (1 day)"
    )
    parser.add_argument(
        "--days", 
        type=int, 
        help="Override number of days to look back (useful for custom ranges)"
    )
    parser.add_argument(
        "--debug-schema", 
        action="store_true", 
        help="Print database schema and exit"
    )
    
    args = parser.parse_args()
    
    if args.debug_schema:
        debug_database_schema()
        return
    
    # Determine how many days to look back
    if args.days:
        days_back = args.days
        print(f"Custom mode: Looking back {days_back} days")
    elif args.mode == "populate":
        days_back = 30  # Look back 30 days for initial population
        print("Populate mode: Looking back 30 days to populate database")
    else:  # daily mode
        days_back = 7   # Look back 7 days for daily runs (catches delayed emails)
        print("Daily mode: Looking back 7 days for new applications")
    
    # Run the email processing
    fetch_recent_emails(days_back=days_back)

if __name__ == "__main__":
    main()