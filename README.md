# clean_inbox.py

A command-line tool that helps you clean up your Gmail inbox by grouping unread emails by sender and letting you review them in batches.

---

## What it does

* Fetches all unread Gmail messages
* Groups them by sender (sorted by largest groups first)
* Shows a preview of subjects for each sender
* Prompts you to:

  * Delete (move to Trash)
  * Mark as read
  * Skip
  * Quit

---

## Setup

1. Install dependencies:

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

2. Enable the Gmail API and download credentials:

* Go to https://console.cloud.google.com/
* Create or select a project
* Enable **Gmail API**
* Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
* Application type: **Desktop App**
* Download the JSON file and save it as `credentials.json` in this directory

---

## Run

```bash
python clean_inbox.py
```

On first run, a browser window will open to authorize access. A `token.json` file will be saved for future runs.

---

## Options

```bash
python clean_inbox.py --dry-run
```

* `--dry-run`
  Simulates actions without modifying any emails

---

## Notes

* Only unread emails are processed
* Deleted emails are moved to Trash (recoverable for 30 days)
* Requires Gmail API access with `gmail.modify` scope
