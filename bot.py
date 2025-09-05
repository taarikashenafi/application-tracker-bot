# bot.py
# pip install: notion-client python-dotenv
import os, imaplib, email, re, datetime
from notion_client import Client

NOTION_TOKEN         = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID   = os.environ["NOTION_DATABASE_ID"]
IMAP_HOST            = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_USER            = os.environ["IMAP_USER"]          # your full email
IMAP_PASS            = os.environ["IMAP_PASS"]          # app password (Gmail) or account password (IMAP)
IMAP_FOLDER          = os.environ.get("IMAP_FOLDER", "INBOX")
IMAP_SINCE_DAYS      = int(os.environ.get("IMAP_SINCE_DAYS", "7"))  # look back n days each run

notion = Client(auth=NOTION_TOKEN)

# --- subject lines to status mapping ---
SUBJECT_RULES = [
    (re.compile(r"thanks for applying|application received|we received your application", re.I), "Applied"),
    (re.compile(r"interview|phone screen|assessment|coding challenge", re.I), "Interview"),
    (re.compile(r"offer", re.I), "Offer"),
    (re.compile(r"not move forward|reject|regret|declined|unsuccessful", re.I), "Rejected"),
]

def parse_company_and_role(subject, body):
    """best-effort extraction. improve with your own patterns as needed."""
    # try "Company – Role" or "Role at Company"
    m = re.search(r"(.+?)\s+[-–]\s+(.+)", subject)
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        # guess which is company vs role:
        if " at " in subject.lower():
            # e.g., "Software Engineering Intern at Figma"
            role = left
            company = right
        else:
            # e.g., "Figma – Software Engineering Intern"
            company = left
            role = right
        return company, role

    m2 = re.search(r"(.+?)\s+at\s+(.+)", subject, re.I)
    if m2:
        role = m2.group(1).strip()
        company = m2.group(2).strip()
        return company, role

    # fallback: try typical job-site footer lines in body
    m3 = re.search(r"Company:\s*(.*)", body)
    m4 = re.search(r"Position|Role:\s*(.*)", body)
    company = m3.group(1).strip() if m3 else None
    role    = m4.group(1).strip() if m4 else None
    return company, role

def derive_status(subject, body):
    for rx, status in SUBJECT_RULES:
        if rx.search(subject) or rx.search(body):
            return status
    return "Saved"  # default if nothing matches

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
    props = {
        "Company Name": {"title": [{"text": {"content": company or "(unknown company)"}}]},
        "Role / Position": {"rich_text": [{"text": {"content": role or "(unknown role)"}}]},
        "Application Status": {"select": {"name": status}},
    }
    if url:         props["Application Link / Portal"] = {"url": url}
    if applied_on:  props["Application Date"] = {"date": {"start": applied_on}}
    if location:    props["Location"] = {"rich_text": [{"text": {"content": location}}]}
    if notes:       props["Notes"] = {"rich_text": [{"text": {"content": notes[:1900]}}]}

    page_id = find_existing(url=url, company=company, role=role)
    if page_id:
        notion.pages.update(page_id=page_id, properties=props)
        return "updated"
    else:
        notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
        return "created"

def fetch_recent_emails():
    since_date = (datetime.date.today() - datetime.timedelta(days=IMAP_SINCE_DAYS)).strftime("%d-%b-%Y")
    M = imaplib.IMAP4_SSL(IMAP_HOST)
    M.login(IMAP_USER, IMAP_PASS)
    M.select(IMAP_FOLDER)
    # narrow subjects you care about; edit as you like:
    search_query = f'(SINCE {since_date})'
    typ, data = M.search(None, search_query)
    ids = data[0].split() if data and data[0] else []
    for eid in ids:
        typ, msg_data = M.fetch(eid, "(RFC822)")
        if typ != "OK": continue
        msg = email.message_from_bytes(msg_data[0][1])
        subj = email.header.make_header(email.header.decode_header(msg.get("Subject") or ""))
        subject = str(subj)
        # only consider likely application emails:
        if not re.search(r"apply|application|interview|assessment|offer|declin|reject|next steps|thanks", subject, re.I):
            continue

        # get body (plain text best)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break
        else:
            if msg.get_content_type() == "text/plain":
                body = msg.get_payload(decode=True).decode(errors="ignore")

        status = derive_status(subject, body)
        company, role = parse_company_and_role(subject, body)

        # try to grab first URL in body as portal link
        url_match = re.search(r"https?://\S+", body)
        url = url_match.group(0) if url_match else None

        applied_on = datetime.date.today().isoformat() if status in ("Applied", "Saved") else None
        result = upsert(company, role, status, url=url, applied_on=applied_on, notes=subject)
        print(f"{result}: {company=} {role=} {status=} {url=}")
    M.logout()

if __name__ == "__main__":
    fetch_recent_emails()