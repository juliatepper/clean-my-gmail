"""
clean_inbox.py
Groups all unread Gmail messages by sender, then prompts you one sender
at a time to decide whether to delete them.

Setup:
1. Install dependencies:
       pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

2. Enable the Gmail API and download credentials:
   - Go to https://console.cloud.google.com/
   - Create a project (or select one)
   - Enable the Gmail API
   - Go to APIs & Services > Credentials > Create Credentials > OAuth 2.0 Client ID
   - Application type: Desktop App
   - Download the JSON and save it as 'credentials.json' in the same folder as this script

3. Run:
       python clean_inbox.py

   On first run, a browser window will open asking you to authorize access.
   After that, a token.json file is saved so you won't be prompted again.
"""

import argparse
import os
import sys
from collections import defaultdict
import re
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

PATTERNS = [
    re.compile(r"unsubscribe", re.I),
    re.compile(r"email\s+preferences?", re.I),
    re.compile(r"opt[\s-]?out", re.I),
    re.compile(r"manage\s+preferences", re.I),
    re.compile(r"update\s+preferences", re.I),
    re.compile(r"stop\s+receiving", re.I),
]

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def authenticate() -> Credentials:
    """Authenticate via OAuth and return credentials."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                sys.exit(
                    f"ERROR: '{CREDENTIALS_FILE}' not found.\n"
                    "Download it from Google Cloud Console and place it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def fetch_all_unread(service) -> list[dict]:
    """Return metadata for every unread message in the inbox."""
    messages = []
    page_token = None

    print("Fetching unread emails", end="", flush=True)
    while True:
        kwargs = {
            "userId": "me",
            "q": "is:unread",
            "maxResults": 500,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().messages().list(**kwargs).execute()
        batch = response.get("messages", [])
        messages.extend(batch)
        print(".", end="", flush=True)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    print(f" {len(messages)} found.\n")
    return messages


def get_message_metadata(service, msg_id: str) -> dict:
    """Fetch From and Subject headers for a single message."""
    msg = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=["From", "Subject"],
        )
        .execute()
    )
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    raw_from = headers.get("From", "")
    name, email = parseaddr(raw_from)

    return {
        "id": msg_id,
        "from": headers.get("From", "(unknown sender)"),
        "email": email or "(unknown sender)",
        "subject": headers.get("Subject", "(no subject)"),
    }


def group_by_sender(messages: list[dict]) -> dict[str, list[dict]]:
    """Group message metadata dicts by their email field, sorted by count descending."""
    groups = defaultdict(list)
    for m in messages:
        groups[m["email"]].append(m)
    return dict(sorted(groups.items(), key=lambda x: len(x[1]), reverse=True))


def mark_as_read(service, msg_ids: list[str]) -> tuple[int, int]:
    """Mark a list of message IDs as read."""
    success, failed = 0, 0
    try:
        service.users().messages().batchModify(
            userId="me",
            body={
                "ids": msg_ids,
                "removeLabelIds": ["UNREAD"]
            }
        ).execute()
        success = len(msg_ids)
    except HttpError as e:
        print(f"    ✗ Error on {msg_ids}: {e}")
        success = 0
        failed = len(msg_ids)
    return success, failed


def delete_messages(service, msg_ids: list[str]) -> tuple[int, int]:
    """Trash a list of message IDs."""
    success, failed = 0, 0
    try:
        service.users().messages().batchModify(
            userId="me",
            body={
                "ids": msg_ids,
                "addLabelIds": ["TRASH"]
            }
        ).execute()
        success = len(msg_ids)
    except HttpError as e:
        print(f"    ✗ Error on {msg_id}: {e}")
        success = 0
        failed = len(msg_ids)
    return success, failed


def prompt_user(sender: str, count: int, subjects: list[str]) -> str:
    """Display sender info with a subject preview and return the user's choice."""
    print("-" * 60)
    print(f"Sender : {sender}")
    print(f"Subjects preview:")
    # TODO: Might be good to show the user what the sender info is too.
    for subject in subjects[:5]:
        print(f"  • {subject}")
    if len(subjects) > 5:
        print(f"  ... and {len(subjects) - 5} more")
    print()

    while True:
        choice = input(
            f"[{count}] unread email(s) from [{sender}]. Delete these? 1 = Yes, 2 = Mark as read, 3 = Skip, q = Quit: "
        ).strip()
        if choice in ("1", "2", "3", "q"):
            return choice
        print("  Please enter one of [1, 2, 3, q].")


def main():
    parser = argparse.ArgumentParser(
        description="Review and delete unread Gmail emails grouped by sender."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run instead of deleting emails.",
    )
    args = parser.parse_args()

    print("Authenticating with Gmail...")
    creds = authenticate()
    service = build("gmail", "v1", credentials=creds)

    # Step 1: Fetch all unread message IDs
    raw_messages = fetch_all_unread(service)
    if not raw_messages:
        print("No unread emails found!")
        return

    # Step 2: Fetch From + Subject metadata for each message
    print("Fetching sender info", end="", flush=True)
    metadata = []
    for i, m in enumerate(raw_messages):
        metadata.append(get_message_metadata(service, m["id"]))
        if (i + 1) % 20 == 0:
            print(".", end="", flush=True)
    print(" done.\n")

    # Step 3: Group by sender (most emails first)
    grouped = group_by_sender(metadata)
    total_senders = len(grouped)
    trash_action_word = "kept" if args.dry_run else "moved to Trash"
    mark_as_read_action_word = "kept" if args.dry_run else "marked as read"

    print(f"Found {len(raw_messages)} unread email(s) across {total_senders} sender(s).")
    print(f"Senders are sorted from most to fewest emails.")
    print(f"Deleted emails will be {trash_action_word}.\n")

    total_deleted = 0
    total_marked_as_read = 0
    total_failed = 0
    total_skipped = 0

    for idx, (sender, msgs) in enumerate(grouped.items(), 1):
        print(f"\n[{idx} of {total_senders}]")
        subjects = [m["subject"] for m in msgs]
        choice = prompt_user(sender, len(msgs), subjects)

        if choice.lower() == "q": break
        elif choice == "1":
            ids = [m["id"] for m in msgs]
            if args.dry_run: 
                ok = 0
                fail = 0
            else:
                ok, fail = delete_messages(service, ids)
            total_deleted += ok
            total_failed += fail
            print(f"  ✓ {ok} email(s) {trash_action_word}.")
        elif choice == "2":
            ids = [m["id"] for m in msgs]
            if args.dry_run: 
                ok = 0
                fail = 0
            else:
                ok, fail = mark_as_read(service, ids)
            total_marked_as_read += ok
            total_failed += fail
            print(f"  ✓ {ok} email(s) {mark_as_read_action_word}.")


        else:
            total_skipped += len(msgs)
            print("  Skipped.")

    print("\n" + "=" * 60)
    print("Session complete.")
    print(f"  Deleted : {total_deleted}")
    print(f"  Skipped : {total_skipped}")
    print(f"  Marked as read : {total_marked_as_read}")
    if total_failed:
        print(f"  Failed  : {total_failed}")
    if total_deleted:
        print("\nDeleted emails are in Trash and recoverable for 30 days.")


if __name__ == "__main__":
    main()