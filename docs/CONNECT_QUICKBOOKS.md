# Connect TruAgent to QuickBooks — Admin Setup Guide

**Updated:** 2026-06-15
**Who this is for:** the person setting up the QuickBooks → TruAgent connection.
**Time:** about 20–30 minutes.

---

## What this does

It automatically copies **invoices** and **expenses** from QuickBooks into TruAgent,
so each job shows real **revenue, cost, and profit**. You do *not* connect
QuickBooks to TruAgent directly — a free tool called **Zapier** sits in the middle
and forwards the data.

```
QuickBooks  ──►  Zapier  ──►  TruAgent
 (invoice or      (forwards     (records it on the
  expense)         the data)     matching job)
```

You will build **two Zaps**: one for invoices, one for expenses. They're almost
identical.

---

## Before you start — get the password ("secret")

Every message TruAgent accepts must include a shared password called the
**QUICKBOOKS_SECRET**. It is **already set** on the server — do **not** invent a new
one. You just need to copy the existing value so Zapier can include it.

**Where to find it:**
1. Go to **Railway** (railway.app) and open the project **valiant-generosity**.
2. Click the **TruAgent** service.
3. Open the **Variables** tab.
4. Find **`QUICKBOOKS_SECRET`** and copy its value. Keep it handy for the steps below.

> If you don't have Railway access, ask Fred for the `QUICKBOOKS_SECRET` value.
> Treat it like a password — don't email it around or paste it into chats.

**The TruAgent address you'll send to (same for both Zaps):**

```
https://truagent-production.up.railway.app/quickbooks/webhook
```

---

## Part 1 — Invoices Zap (money coming IN)

### Step 1. Start the Zap
1. Log into **[Zapier](https://zapier.com)**.
2. Click **Create → Zap**.

### Step 2. Trigger = a new QuickBooks invoice
1. For the **Trigger**, choose **QuickBooks Online**.
2. Event: **New Invoice**.
3. Connect your QuickBooks account when prompted, and **Test** it so Zapier pulls a
   sample invoice.

### Step 3. Action = send it to TruAgent
1. For the **Action**, choose **Webhooks by Zapier**.
2. Event: **POST**.
3. Fill in the fields exactly like this:

| Field | What to put |
|---|---|
| **URL** | `https://truagent-production.up.railway.app/quickbooks/webhook` |
| **Payload Type** | `json` |
| **Wrap Request In Array** | **No** |

4. Under **Data**, add these rows (left = the name, right = the QuickBooks value you
   pick from the dropdown):

| Name (type exactly) | Value (pick from QuickBooks) |
|---|---|
| `secret` | *(paste the QUICKBOOKS_SECRET value)* |
| `transaction_type` | type the word `invoice` |
| `transaction_id` | Invoice **Id** |
| `amount` | Total **Amount** |
| `date` | Invoice **Date** *(or Txn Date)* |
| `job_id` | the **job number** *(see "Linking to the right job" below)* |
| `customer_name` | Customer **Name** |
| `status` | Invoice **Status** *(optional)* |
| `description` | a memo/description *(optional)* |

5. **Test** the action. A green success means TruAgent accepted it.

### Step 4. Turn it on
Click **Publish** and make sure the Zap is **On**.

---

## Part 2 — Expenses Zap (money going OUT)

Repeat Part 1 with two differences:

- **Trigger event:** **New Expense** (or **New Bill**, depending on how you record
  costs in QuickBooks).
- **Data rows:** use these instead —

| Name (type exactly) | Value (pick from QuickBooks) |
|---|---|
| `secret` | *(paste the QUICKBOOKS_SECRET value)* |
| `transaction_type` | type the word `expense` |
| `transaction_id` | Expense/Bill **Id** |
| `amount` | **Amount** |
| `date` | Expense **Date** |
| `job_id` | the **job number** *(see below)* |
| `vendor_name` | Vendor **Name** |
| `category` | **Category/Account** *(optional)* |
| `description` | Memo/**Description** *(optional)* |

Publish and turn it **On**.

---

## Linking to the right job (important)

TruAgent uses the **`job_id`** value to attach the invoice/expense to a specific
job. For the money to land on the right job, `job_id` should be the **same job
number that job has in Roofr** (TruAgent now matches a QuickBooks transaction to a
job by that Roofr job number *or* TruAgent's own job id).

**How to make sure it's there:** put the job/Roofr number on the QuickBooks
transaction — most shops use the **Customer/Sub-customer (Job)** field, a **custom
field**, or the **memo** — and map that field to `job_id` in the Zap.

**If `job_id` is blank or unknown:** that's okay — the invoice/expense is still
recorded and shows up in the **company-wide** totals; it just won't be tied to one
specific job until a matching id is added.

---

## How to confirm it's working

1. **In QuickBooks:** create one small **test invoice** (and one test expense).
2. **In Zapier:** open the Zap → **Zap History**. A successful run shows a green
   check. If you see an error, read the next section.
3. **In TruAgent:** log in as a **Manager** or **Super Admin**, open a job that has
   the matching job number, and view its **financials** — you should see the test
   amount in revenue (invoice) or cost (expense).
4. Delete the test transactions in QuickBooks when you're done.

---

## If something doesn't work

| What you see in Zapier | What it means | Fix |
|---|---|---|
| **403** error | The `secret` is wrong or missing | Re-copy `QUICKBOOKS_SECRET` from Railway and paste it into the Zap's `secret` row exactly (no extra spaces) |
| **422** or **400** error | A required field is missing or the wrong type | Make sure `secret`, `transaction_type`, `transaction_id`, `amount`, and `date` are all filled. `amount` must be a number; `transaction_type` must be exactly `invoice` or `expense` |
| Success, but it's not on the job | `job_id` didn't match a job | Check the `job_id` value matches the job's Roofr number; if it's blank, add the job number to the QuickBooks transaction |
| Nothing happens at all | The Zap is off, or QuickBooks isn't connected | Make sure the Zap is **On** and the QuickBooks account is connected in Zapier |

**The five fields that are always required:** `secret`, `transaction_type`,
`transaction_id`, `amount`, `date`. Everything else is optional.

---

## Quick reference card

- **Send to:** `https://truagent-production.up.railway.app/quickbooks/webhook`
- **Method:** POST · **Payload:** JSON
- **Password field:** `secret` = the `QUICKBOOKS_SECRET` value from Railway (already set)
- **Two Zaps:** invoices (`transaction_type: invoice`) and expenses (`transaction_type: expense`)
- **Required fields:** `secret`, `transaction_type`, `transaction_id`, `amount`, `date`
- **Recommended:** `job_id` (the Roofr job number) so the money lands on the right job
- **Who can see job financials in TruAgent:** Managers and Super Admins only

---

*Questions or an error you can't place? Send Fred the screenshot of the Zapier
"Zap History" error — it names the exact field or status code.*
