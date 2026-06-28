# TruAgent — Data Model (`db.json`)

All data lives in one JSON file, `db.json`, in the project root. It is created
automatically on first write and seeded with three demo users. It is gitignored
and never committed.

> Note: the file does not exist until the app writes data for the first time.
> Until then, logins are validated against the same seed values held in memory.

## Top-level shape

```json
{
  "users":        { "<email>": { ...user } },
  "jobs":         { "<job_id>": { ...job } },
  "documents":    { "<doc_id>": { ...document } },
  "chat_history": { "<email>": [ ...messages ] },
  "financials":   { "invoices": {}, "expenses": {} }
}
```

## users

Keyed by email.

```json
{
  "email": "fred@trulineroofing.com",
  "password_hash": "<sha256 of the password>",
  "role": "super_admin"   // one of: super_admin | manager | user
}
```

Seeded logins (passwords rotated 2026-06-14, sec-02 — old public demo passwords
retired; strong values in the git-ignored `ROTATED-LOGINS-2026-06-14.txt`):
- `fred@trulineroofing.com` → super_admin
- `office@trulineroofing.com` → manager
- `fieldcrew@trulineroofing.com` → user

## jobs

Keyed by `job_id`. Created locally or synced in from Roofr via Zapier.

```json
{
  "job_id": "1001",
  "client_name": "Acme Warehouse",
  "address": "123 Main St",
  "status": "Pending",
  "workflow_stage": "Lead",        // job lifecycle: Lead → Quote → Approved → Won → In Progress → Complete
                                   //   ("Won" = deal won/ready to schedule; WIP, schedule & anomaly
                                   //    features key off it. DISTINCT from the opportunity *pipeline*
                                   //    stages New Lead…Negotiation/Won/Lost. The convert/Won handoff
                                   //    maps opp stages onto these via _opp_stage_to_job in main.py.)
  "images": [],
  "notes": [ { "note": "...", "added_by": "...", "added_at": "ISO time" } ],
  "invoices": ["INV-1"],           // ids into financials.invoices
  "expenses": ["EXP-1"]            // ids into financials.expenses
}
```

## documents

Keyed by a numeric string id. The file itself is saved under `documents/`.

```json
{
  "id": "1",
  "filename": "estimate.pdf",
  "filepath": "documents/estimate.pdf",
  "description": "",
  "uploaded_by": "fred@trulineroofing.com",
  "uploaded_at": "ISO time"
}
```

## chat_history

Keyed by user email; a list of messages.

```json
[ { "role": "user", "content": "...", "timestamp": "ISO time" },
  { "role": "assistant", "content": "...", "timestamp": "ISO time" } ]
```

## financials

Fed from QuickBooks via Zapier. Two sub-maps:

```json
{
  "invoices": { "<transaction_id>": { "amount": 0, "job_id": "...", "status": "pending", ... } },
  "expenses": { "<transaction_id>": { "amount": 0, "job_id": "...", "category": "...", ... } }
}
```

Profitability per job = sum of linked invoices − sum of linked expenses.
