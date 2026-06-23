# TruAgent → Commercial-Roofing CRM — Roadmap to Completion

**Owner:** Fred (Truline Roofing) · **Maintained by:** Claude Code sessions
**Created:** 2026-06-22 · **Status doc — update the checkboxes + `CRM-BUILD-LOG.md` as you go.**

> **For any session picking this up:** this is the master plan. Read this + `CRM-BUILD-LOG.md`
> (running notes) first. Strategic context (Roofr gap analysis, 1ESX, costs) lives in
> `F:\Claude Sandbox\Projects\truagent-crm\CRM-FEASIBILITY-BRIEF.md`. The legacy
> `BUILD_PROGRESS.md` 63-feature list is **aspirational, not accurate** — a 2026-06-22 code
> audit found most CRM features are backend-only with no UI (see brief). Trust THIS doc.

---

## 0. Goal
Make TruAgent the **system-of-record commercial-roofing CRM** that replaces Roofr-as-pipeline:
wire the existing backend to real screens + automation, fill the genuine gaps, then add
measurements / payments / customer portal. When done, Truline runs a full lead→cash cycle
in TruAgent without Roofr.

## 1. Architecture (current)
- **Backend:** `main.py` (FastAPI, one file). **Storage:** Supabase Postgres, whole-db JSONB
  doc (`app_state` row), via REST — `load_db()/save_db()` (see `CLAUDE.md` / data_model). Unset
  `SUPABASE_URL`+`SUPABASE_SERVICE_KEY` → falls back to `db.json` (rollback).
- **Frontend:** `static/index.html` + `app.js` + `style.css` (vanilla SPA, tab-based).
- **Deploy:** GitHub `DerfEflow/TruAgent` → Railway `valiant-generosity`/TruAgent auto-deploys on
  push to `main`. Live at https://truagent-production.up.railway.app.
- **Cron:** built-in in-process scheduler (`SCHEDULER_ENABLED`, default on) + `/cron/tick` door.

## 2. Roles & permissions model (target)
Three roles enforced server-side (`get_current_user` / `get_manager_or_above` / `get_super_admin`)
and reflected in the UI via `.manager-only` / `.admin-only` classes.

| Area | super_admin (Fred) | manager (office) | user (field crew) |
|---|---|---|---|
| Apps launcher, AI Agent, Jobs, Production, Documents | ✅ | ✅ | ✅ |
| Pipeline / opportunities / convert / win-loss | ✅ | ✅ | ❌ |
| Financials, financial AI tools | ✅ | ✅ | ❌ (stripped) |
| Customers/contacts (new) | ✅ full | ✅ full | 👁 read contact on own jobs only |
| Comms inbox (new) | ✅ | ✅ | ❌ |
| Compliance, Schedule | ✅ | ✅ | 👁 own assignments |
| Admin (users, webhooks) | ✅ | ❌ | ❌ |
| Document delete | ✅ | ❌ | ❌ |

Rule of thumb: **money + customer comms = manager+; operational/field = all roles.** Every new
endpoint must declare its dependency (`Depends(get_manager_or_above)` etc.).

## 3. Connections / integrations & secrets (the "all connections" part)

| Integration | Direction | Mechanism | Env var(s) | Status | Needed for |
|---|---|---|---|---|---|
| Database | — | Supabase REST | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | ✅ LIVE | everything |
| Roofr CRM | inbound | Zapier → `/zapier/webhook` | `ZAPIER_SECRET` | ✅ LIVE | jobs from Roofr |
| Roofr CRM | outbound | `/roofr/update` → webhook | `ROOFR_WEBHOOK_URL` | ⚠️ dormant | **BLOCKED: Zapier Roofr app has no update-job action** — needs Roofr REST API key or stays inbound-only |
| Alpha Estimator | inbound | TruHub → `/alpha/webhook` | `ALPHA_SECRET` | ✅ LIVE | estimate baselines |
| Delta Coating Log | inbound | TruHub → `/production/webhook` | `PRODUCTION_SECRET` | ✅ LIVE | field/QA data |
| Dominate leads | inbound | `/leads/webhook` | `LEADS_SECRET` | ✅ LIVE | opportunities |
| QuickBooks | inbound | Zapier (2 Zaps) → `/quickbooks/webhook` | `QUICKBOOKS_SECRET` | 🔲 needs Fred OAuth + Zaps (see `docs/CONNECT_QUICKBOOKS.md`) | job financials |
| Email | outbound | Zapier → Gmail/SendGrid | `EMAIL_WEBHOOK_URL` | 🔲 needs Fred OAuth | cadence, review-ask, inbox send |
| SMS | outbound | Zapier → Twilio | `SMS_WEBHOOK_URL` | 🔲 needs Fred OAuth | cadence, inbox send |
| Email/SMS | **inbound** | Zapier email-parser / Twilio inbound → `/inbox/webhook` | `INBOX_SECRET` | ⚙️ code LIVE; needs Fred to set `INBOX_SECRET` + wire the Zaps | unified comms inbox |
| E-signature | both | `/pipeline/{id}/esign-send` + `/esign/webhook` | `ESIGN_WEBHOOK_URL`, `ESIGN_SECRET` | ⚠️ partial (no UI, url unset) | proposals |
| 1ESX measurements | both | 1ESX REST API | `ESX_API_KEY` (new) | 🔲 NEW (Phase 3) | roof measurements |
| Stripe payments | both | Stripe API + webhook | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (new) | 🔲 NEW (Phase 3) | collect payment |
| Cron/scheduler | — | in-process + `/cron/tick` | `CRON_SECRET`, `SCHEDULER_ENABLED` | ✅ LIVE | cadence/SLA/review timers |

**Fred-gated items** (need his accounts/OAuth, can't be done autonomously): QuickBooks Zaps,
Email/SMS connect, Roofr API key (or accept inbound-only), 1ESX account, Stripe account.

---

## 4. Phase 1 — Make the CRM you already have actually work
*Mostly wiring existing backend to UI + adding a few cron timers. High ROI, low risk.*

- [x] **P1-1. Opportunity ↔ Job link + convert-to-job** *(DONE 2026-06-22, commit 50bc569)*
  Backend `POST /pipeline/{id}/convert` (manager+): create/link a job from an opp, set
  `opp.job_id` ↔ `job.origin_opportunity_id`. Idempotent. UI: "Convert to Job" on pipeline cards.
  *Acceptance met:* converting an opp creates/links a job; `opp.job_id` is set; the Won-stage sync &
  e-sign auto-Won now fire. Verified via TestClient (create→convert→idempotent→Won-handoff→403 for field crew).
- [x] **P1-2. Win/Loss UI + analytics surfacing.** Mark won/lost on a card (`POST /pipeline/{id}/win-loss`);
  render the `by_loss_reason` + `by_rep` rollups from `/sales/win-loss` (already computed, currently discarded).
- [x] **P1-3. Cadence → real engine.** Add `due_at` to cadence steps + a cron task that flags overdue
  follow-ups; "Follow-ups due" view. (`/pipeline/{id}/cadence` exists; no timer/UI today.)
- [x] **P1-4. Drain review-request queue + referral capture.** Cron flush queued review-asks via
  email/SMS outbox; add referral capture field/endpoint. (`/job/{id}/review-request` queues, nothing sends.)
- [x] **P1-5. Lead SLA enforcement.** Cron rule flags opps past `sla_due` with no first touch; surface on dashboard.
- [x] **P1-6. Rep/territory performance UI + territory field.** Surface orphaned `/sales/performance`; add a territory dimension.
- [x] **P1-7. Real kanban.** Drag-and-drop stage changes; card shows value/age/next-action; reconcile stage list.
- [x] **P1-8. Opportunity/Job detail view.** Read the existing `timeline` + `comm-log` (both stored, neither shown).

## 5. Phase 2 — Build the genuine gaps (net-new)
- [x] **P2-9. Customer/contact entity.** First-class `customers` with many contacts, linked to jobs/opps
  (today customers are loose strings). Migration + UI + link from jobs/opps.
- [x] **P2-10. Unified comms inbox** *(DONE 2026-06-22)*. Inbound email/SMS door `POST /inbox/webhook`
  (secret `INBOX_SECRET`) → `db.messages`, auto-linked to job/opp by contact; threaded per contact
  (`GET /inbox`, `GET /inbox/thread`, `POST /inbox/thread/read`); send from thread `POST /inbox/send`
  (manager+, dormant-safe via email/SMS outbox). UI: "Inbox" tab (manager-only), thread list + reply.
  *Sending/receiving live needs Fred: set EMAIL_/SMS_WEBHOOK_URL + INBOX_SECRET, wire Zapier email-parser
  + Twilio inbound (see §3).*
- [x] **P2-11. Material ordering from estimate.** Generate a PO/order from Alpha `est_gallons` → email to supplier.
- [x] **P2-12. Stage-change automation.** Rules engine: stage X → create task / notify rep / start cadence.
- [x] **P2-13. Lead-source attribution / ROI.** Win-rate + revenue by source (extends win/loss rollups).

## 6. Phase 3 — The bigger build
- [ ] **P3-14. 1ESX measurements integration** (order → parse XML area/parapet/penetrations → pre-fill Alpha). Brief §4.
- [x] **P3-15 (Stripe payments) DONE 2026-06-22.** `POST /job/{id}/payment-link` (manager+) →
  Stripe Checkout link (Truline account, `STRIPE_API_KEY`); `POST /stripe/webhook` (HMAC-verified,
  `STRIPE_WEBHOOK_SECRET`) marks the job paid + records a financials invoice; "Request payment" button
  in the customer 360. Verified live (link created + expired, signed webhook marks paid). *Proposals
  polish (templated proposal doc) still TODO under this item.*
- [ ] **P3-16. Customer portal** (view / sign / pay / track).

## 7. Cross-cutting (do alongside)
- [ ] Reconcile pipeline **stage vocabulary** across lead door, `/pipeline`, and UI (currently mismatched).
- [ ] Per-feature **permission** checks as each item ships (see §2).
- [ ] Keep `CRM-BUILD-LOG.md` updated every working session.
- [ ] Treat `BUILD_PROGRESS.md` as legacy; this roadmap supersedes it for CRM work.

## 8. Status legend
`[ ]` not started · `[~]` in progress (see build log) · `[x]` done + deployed + verified.

## 9. Resume-here
Newest session: read `CRM-BUILD-LOG.md` bottom entry for exactly where the last one stopped.
