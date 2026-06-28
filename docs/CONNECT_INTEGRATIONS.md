# TruAgent — Integrations Setup Guide (step by step)

**For:** Fred. **Updated:** 2026-06-22. Wire these to turn on the CRM features that are
built but dormant. Each integration is independent — do them in any order.

> **Key concept — TruAgent is INTERNAL.** Your staff use TruAgent. Anything customer-facing
> (paying, signing) happens on the *integration's own hosted page*, reached by a link TruAgent
> emails. Customers never log into TruAgent. Stripe = how customers pay you; the checkout page
> is Stripe's, not TruAgent's.

**TruAgent address (used below):** `https://truagent-production.up.railway.app`

---

## 0. The one repeated task: setting a Railway variable
Several steps say "set VARNAME on Railway." Here's how, once:
1. Go to **railway.app** → project **valiant-generosity** → service **TruAgent**.
2. Open the **Variables** tab → **New Variable** (or edit existing).
3. Enter the name (e.g. `EMAIL_WEBHOOK_URL`) and value → **Add/Save**. Railway redeploys automatically.

> **Or hand it to Claude:** paste me the value (e.g. a Zapier hook URL) and I'll set it for you and verify.
> I can also generate the secrets (`INBOX_SECRET`) myself — you'd just copy them from Railway into the Zap.

Generate a strong secret when one is needed: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

---

## 1. Outbound Email  (powers: cadence reminders, review-asks, inbox replies, material orders)
**Goal:** TruAgent → Zapier → your Gmail/SendGrid sends the email.

1. In **Zapier**, **Create Zap**.
2. **Trigger:** *Webhooks by Zapier* → **Catch Hook** → Continue. Zapier shows a **custom webhook URL** — copy it.
3. **Action:** *Gmail* (or *SendGrid*) → **Send Email**. Connect your account when asked.
4. Map the fields (TruAgent sends these exact names):
   - **To** = `to`
   - **Subject** = `subject`
   - **Body** = `body`
5. **Publish** the Zap (turn it **On**).
6. **Set on Railway:** `EMAIL_WEBHOOK_URL` = the Catch Hook URL from step 2.
7. **Test:** in TruAgent, open a customer in the **Inbox** and send a reply — it should arrive in the customer's email. (Queued emails also flush automatically once this is set.)

---

## 2. Outbound SMS  (powers: SMS cadence, inbox text replies)
**Goal:** TruAgent → Zapier → Twilio sends the text.

1. **Zapier → Create Zap.**
2. **Trigger:** *Webhooks by Zapier* → **Catch Hook** → copy the URL.
3. **Action:** *Twilio* → **Send SMS**. Connect your Twilio account (needs a Twilio number).
4. Map:
   - **To Number** = `to`
   - **Message** = `message`
   - **From Number** = your Twilio number.
5. **Publish.**
6. **Set on Railway:** `SMS_WEBHOOK_URL` = the Catch Hook URL.

---

## 3. Inbound Inbox — Email  (incoming customer emails show up in the Inbox tab)
**Goal:** a customer's email → Zapier → TruAgent records it, threaded to the right customer/job.

1. First set the door secret: **set on Railway** `INBOX_SECRET` = a strong secret (or let Claude generate it).
2. **Zapier → Create Zap.**
3. **Trigger:** either *Email by Zapier* (**New Inbound Email** — Zapier gives you a forwarding address; auto-forward your sales inbox to it), **or** *Gmail* → **New Email**.
4. **Action:** *Webhooks by Zapier* → **POST**.
   - **URL:** `https://truagent-production.up.railway.app/inbox/webhook`
   - **Payload Type:** `json`
   - **Data:**
     - `secret` = *(the INBOX_SECRET value — copy from Railway)*
     - `channel` = `email`
     - `contact` = the sender's email address (the "From")
     - `subject` = the email subject
     - `body` = the email body
     - `name` = the sender's name *(optional)*
5. **Publish.**
6. **Test:** send an email from an address that matches a job/opportunity's contact → it appears in TruAgent's **Inbox**, linked to that customer.

---

## 4. Inbound Inbox — SMS  (incoming texts show up in the Inbox)
1. Uses the same `INBOX_SECRET` from §3.
2. In **Twilio**, set your number's **inbound message webhook** to a Zapier Catch Hook (or use the *Twilio → New SMS* Zapier trigger).
3. **Action:** *Webhooks by Zapier* → **POST** to `…/inbox/webhook` with:
   - `secret` = INBOX_SECRET · `channel` = `sms` · `contact` = the sender's phone number · `body` = the message text.
4. **Publish.**

---

## 5. QuickBooks  (live job revenue & cost)
Full walkthrough already exists: **`docs/CONNECT_QUICKBOOKS.md`**. In short — two Zaps
(invoices + expenses), QuickBooks trigger → Webhooks POST to
`…/quickbooks/webhook` with `secret` = `QUICKBOOKS_SECRET` (already set on Railway),
`transaction_type` (`invoice`/`expense`), `transaction_id`, `amount`, `date`, and `job_id`
(use the job's Roofr number so it lands on the right job).

---

## 6. Roof Measurements — DIY estimator  *(P3-14 — BUILT, works with no setup)*
The **Measure** tab estimates building footprint + roof area from an address using **free, keyless**
open data (OpenStreetMap building footprints + Nominatim geocoding). Nothing to turn on — it works
today. Geometry does the measuring; AI only verifies. **Always field-verify before ordering materials.**

How you use it: open **Measure** → type an address (or a job id) → **Estimate** → confirm the right
building if several are found → optionally **AI verify** → **Pre-fill Alpha baseline** to push the roof
area into a job's estimate.

**Optional upgrades (Fred-gated — none are required):**
- **Google Solar cross-check** — a second roof-area opinion. Create a Google Cloud project, enable the
  **Solar API**, get a key, **set on Railway:** `GOOGLE_SOLAR_API_KEY`. Then tick "Solar cross-check".
- **Microsoft footprints** — only if you host a point-query service for the MS dataset; **set on Railway:**
  `MS_FOOTPRINTS_URL`. (There is no free point API for raw MS data, so this stays off by default.)
- **Paid 1ESX** — only if you later want survey-grade numbers *alongside* DIY. Create an account at
  **1esx.com**, request API access, give Claude the key + docs, **set on Railway:** `ESX_API_KEY`.
> Before trusting any source for bids, compare it to one known Truline roof you've measured yourself.

---

## 7. Stripe Payments  *(P3-15 BUILT; payment links + customer-portal pay + paid webhook)*
**This is how customers pay you. TruAgent stays internal; customers pay on Stripe's page.**
1. Create/log into **Stripe**. In the Dashboard → **Developers → API keys**, get the **Secret key**
   (the `sk_live_…` for the Trulineroofing account). The **publishable key is NOT needed** — the
   hosted-Checkout flow is fully server-side.
2. **Developers → Webhooks** → add an endpoint
   `https://truagent-production.up.railway.app/stripe/webhook`, subscribe to
   `checkout.session.completed`, and copy the **Signing secret** (`whsec_…`).
3. **Set on Railway (two variables):**
   - `STRIPE_API_KEY` = the secret key  *(or name it `TRUAGENT_STRIPE_SECRET_KEY` — the app accepts
     either)*
   - `STRIPE_WEBHOOK_SECRET` = the signing secret  *(or `TRUAGENT_STRIPE_WEBHOOK_SECRET`)*
> Once both are set, the "Request payment" button, the customer-portal **Pay** button, and the paid
> webhook all go live. Until then payment cleanly reports "not configured".

---

## Quick status checklist
| Integration | You provide | Claude does | Variable |
|---|---|---|---|
| Outbound email | Gmail/SendGrid + the Zap | set var + verify | `EMAIL_WEBHOOK_URL` |
| Outbound SMS | Twilio + the Zap | set var + verify | `SMS_WEBHOOK_URL` |
| Inbox email-in | the Zap | generate/set secret + verify | `INBOX_SECRET` |
| Inbox SMS-in | Twilio + the Zap | (same secret) | `INBOX_SECRET` |
| QuickBooks | connect QBO + 2 Zaps | already set | `QUICKBOOKS_SECRET` |
| 1ESX (P3) | account + API key | build + wire | `ESX_API_KEY` |
| Stripe (P3) | account + keys | build + wire | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
