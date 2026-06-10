# TruAgent — Session Handoff
_Last updated: 2026-06-09_

---

## Current State: LIVE on Railway

**Production URL:** https://truagent-production.up.railway.app  
**GitHub repo:** https://github.com/DerfEflow/TruAgent  
**Local dev:** http://localhost:5050 (run `.\.venv\Scripts\python.exe main.py`)

**Auto-deploy:** Every `git push origin main` triggers a Railway redeploy automatically.

---

## What's Done

### Design
- Full dark steel theme (carbon black + Truline green)
- Franchise-quality design across all 6 screens
- Mobile responsive: 768px + 480px breakpoints
- Header email hidden on mobile, tabs scroll horizontally
- Clipped-corner buttons, green status dot, industrial typography

### AI Chat
- Model: `gpt-5.5` (confirmed working on Railway)
- Parameters: `max_completion_tokens=1000` only (gpt-5.5 rejects `temperature` and `max_tokens`)
- Voice input: mic button using OpenAI Whisper (`/transcribe` endpoint)
  - MediaRecorder API in browser → POST audio → Whisper → text into input field
  - Tap to record (turns red), tap again to stop → text appears in chat box

### Deployment
- `railway.toml` and `requirements.txt` added
- All 4 env vars set in Railway: `OPENAI_API_KEY`, `SESSION_SECRET`, `ZAPIER_SECRET`, `QUICKBOOKS_SECRET`
- `PORT` is set automatically by Railway — do not set manually

### Webhook fixes
- `GET /zapier/webhook` added for Zapier URL verification (returns `{"status":"ok"}`)
- `POST /zapier/webhook` handles actual job data from Roofr

---

## Roofr → TruAgent Zap: LIVE ✅ (Job Workflow Stage Changed)

The first Roofr Zap works end-to-end: Roofr → Zapier (Webhooks by Zapier → POST, Payload Type **JSON**) → `/zapier/webhook` → job appears in the Jobs tab with enriched data.

**Webhook now accepts ANY fields** Roofr/Zapier sends — no code change needed to add a field. Empty test records (no `job_id`) are accepted but store nothing. Array-wrapped / stringified / form-encoded bodies are all normalized, so Zapier's "Wrap Request In Array = Yes" no longer breaks it (commit `9e1aea8`). Enriched card + arbitrary-field storage in commit `e201ddc`.

**Field mapping (Zapier Data section — left = key typed exactly; right = pick the Roofr field from the dropdown so it becomes a dynamic tag, NOT typed text):**

| TruAgent key | Roofr field | Shows on card as |
|---|---|---|
| `secret` | fixed ZAPIER_SECRET value | (auth only) |
| `job_id` | External Id | small row |
| `job_name` | Job / Project Name | **big headline** |
| `client_name` | Primary Customer Name | Customer row |
| `customer_phone` | Customer Phone | Phone row |
| `customer_email` | Customer Email | Email row |
| `job_value` | Job Value / Contract Amount | **green $ value** |
| `assigned_to` | Assigned Rep / Salesperson | Assigned row |
| `address` | Job Address | Address row |
| `status` | New Stage | status badge |

Any *extra* key mapped also displays (catch-all renderer). Frontend lives in `static/app.js` (`refreshJobs()` + `formatMoney()`) with styles `.job-card h3` / `.job-value`.

## In Progress: Roofr "Lead Created" Zap (2nd Zap)

Building now. **No code change / no redeploy needed** — the webhook already accepts any fields. Same POST action (same URL, Payload Type JSON) as the Stage-Changed Zap, but the Lead Created trigger exposes a *different* field set. Confirmed mapping (left = key typed exactly; right = pick the lead field from the dropdown unless it says "type"):

| TruAgent key | Roofr Lead field |
|---|---|
| `secret` | *type* the ZAPIER_SECRET value |
| `job_id` | ID |
| `client_name` | Lead Name (becomes the card headline) |
| `customer_phone` | Lead Phone |
| `customer_email` | Lead Email |
| `address` | Address |
| `status` | *type* the literal text: `New Lead` |
| `estimate` | Estimates Generated |
| `material` | Property Desired Material |
| `property_type` | Property Type |
| `square_footage` | Total Square Footage |
| `lead_notes` | Lead Notes |

Decisions: leave `job_name` empty (Lead Name is the headline); do NOT map `job_value` — the only money field ("Estimates Generated") is a text range and would garble through `formatMoney`, so it goes in `estimate` instead; use key `lead_notes` NOT `notes` (the bare key `notes` is reserved as a list — a string there breaks card rendering). Zapier "Enhanced field mappings" toggle = not needed.

**State at handoff:** Fred was about to click **Test action** on this Zap.

**Deferred polish:** ✅ DONE (2026-06-09) — added a `.status-new-lead` / `.status-lead` / `.status-new` green badge style. Bundled (not yet deployed) with the larger 2026-06-09 change set below; goes out on the next authorized push.

**Remaining Zaps to build:**
1. **QuickBooks → TruAgent** — two Zaps (invoices + expenses) to `/quickbooks/webhook`
2. **Gmail outbound** — Zapier Catch Hook → Gmail, URL goes in `EMAIL_WEBHOOK_URL` env var on Railway

---

## Session 2026-06-09 — AI agent upgrade + fixes (STAGED LOCALLY, not yet deployed)

All of the below is committed-ready in the working copy but **not pushed** — it goes out on Fred's next authorized push to `main` (which auto-deploys and, per caveat #7, wipes `db.json`). Verified locally end-to-end.

**1. `/chat` is now a real tool-calling agent (the headline change).** Previously the AI only *talked about* doing things (it injected the whole DB as JSON and returned text — it could not actually update Roofr, add notes, or send anything). It now uses OpenAI tool-calling and actually **executes**:
- `update_job_status`, `add_job_note` — both auto-sync to Roofr when `ROOFR_WEBHOOK_URL` is set (says "synced" / "not configured" / "sync failed").
- `send_email`, `send_sms` — via the existing webhook integrations.
- `list_jobs`, `get_job`, `list_documents` — for answering questions.
- `get_job_financials`, `company_financials_summary` — **manager/super_admin only**, gated server-side (field crew can't reach them, and `get_job` strips invoice/expense lists for field crew).
- This makes "Updating Roofr" and "answering job/accounting/production questions" work through plain English, e.g. *"mark job 1001 in progress"*, *"what's our total revenue?"*, *"add a note to job 2002 that the crew finished prep."*
- Prompt is now **lean** (a compact 40-job summary instead of dumping the entire DB; history trimmed to the last 8 turns) — cheaper tokens, scales as jobs grow.

**2. Bug fixes:**
- Document upload `doc_id` no longer collides after a delete (was `len()+1`, now `max(id)+1`), so uploads can't silently overwrite an existing document's record.
- Uploaded filenames are now sanitized (`os.path.basename` + `doc_id` prefix) — blocks path-traversal and same-name overwrite on disk.

**3. `.status-new-lead` badge** — see Lead Zap section above.

**4. Security/doc hygiene:** scrubbed an old `ZAPIER_SECRET` value (`jSlhh7…`) and dead `*.replit.app` URLs out of `INTEGRATION_GUIDE.md` + `ZAPIER_QUICKSTART.md` and pointed them at the Railway URL. That committed secret was the **rotated-out Replit-era** one (it does NOT match the live Railway/`.env` secret), so it's inert — but it still lives in git history. Optional: rotate `ZAPIER_SECRET` if you want history fully clean.

**5. Jobs tab — deterministic "Update Roofr" controls (closes the headline MVP gap).** Each job card now has a **stage dropdown** (Lead → Quote → Approved → In Progress → Complete) and an **Add note** box. They POST to `/roofr/update`, which now **always saves locally and syncs to Roofr best-effort** (it used to 503 if the *outbound* Roofr webhook wasn't set, losing the update). Shows a sync-status line ("Saved & synced" / "Saved — Roofr sync not set up yet"). Available to all roles (status/notes are operational, not financial — matches what the AI agent already allows). Verified end-to-end on the backend; the *button* path couldn't be screenshotted because this session's preview env was occupied by an unrelated app.

**6. AI model id is now an env var (`OPENAI_MODEL`, default `gpt-5.5`) with graceful fallback** to `OPENAI_FALLBACK_MODEL` (default `gpt-4o-mini`) if the primary id is rejected — so a bad/unavailable model id can't 500 every chat message. Reconciled `docs/architecture.md` (it wrongly said `gpt-4o-mini`).

**7. Atomic `db.json` writes** (`save_db` now writes a temp file then `os.replace`) so a crash mid-write can't corrupt the DB into invalid JSON that fails to boot.

### Planning deliverables added this session (for review / future sessions)
Three new docs in `docs/`, generated from a multi-agent analysis and adversarially reviewed:
- **`FEATURE_CATALOG.md`** — ~50 coating-specific features across production/QA, accounting, sales/CRM, scheduling, office/compliance, and AI, split MVP / fast-follow / later, with a **Top-10 build-next shortlist**.
- **`MVP_GAP_ASSESSMENT.md`** — honest read vs the stated MVP; confirms the 2 real blockers (persistent storage; Roofr-update UI — the latter now done) plus model-id reliability.
- **`APP_INTEGRATION_ROADMAP.md`** — the **configurable** connection architecture for Alpha Estimator / Delta Coating Logistics / Dominate Marketing, incl. the public-vs-internal resale constraint, a "Connections registry" model, the shared identity spine + three-bucket gallon model, per-app data contracts, and a phased plan **for a separate future session**.

**Note for whoever deploys this:** the live AI behavior can't be fully proven until it's on Railway with `OPENAI_API_KEY` + `ROOFR_WEBHOOK_URL` set. Locally the OpenAI key IS present in `.env`, so the agent loop was verified to fire and mutate jobs; the Roofr round-trip only reads "not configured" locally because `ROOFR_WEBHOOK_URL` is blank in the local `.env`.

---

## Remaining To-Do (in priority order)

1. ~~**Finish Roofr Zap**~~ ✅ DONE — Stage-Changed Zap live with enriched fields
2. **Add second Roofr Zap** (Lead Created trigger)
3. **QuickBooks Zaps** (invoices + expenses)
4. **Gmail outbound Zap**
5. **Change demo passwords** before sharing with real staff
   - office@trulineroofing.com / office123 → manager
   - fieldcrew@trulineroofing.com / roof123 → field crew
6. **Test voice input** on mobile (tap mic, speak, check transcription accuracy)
7. **Persistent storage** — ✅ DONE & DEPLOYED 2026-06-09. Railway volume `truagent-volume-pBwm` mounted at `/data` on the **valiant-generosity → TruAgent → production** service (note: there's a second, empty "TruAgent" service in project `earnest-spirit` with no domain — ignore it). `DATA_DIR=/data` set. Commit `f26c3d0` pushed and live; deploy verified (root 200, webhook health JSON, `updateJobStage` marker in deployed app.js). Data now survives redeploys. (Strategic alternative for later: move to Supabase to match the sibling apps — see `docs/APP_INTEGRATION_ROADMAP.md`.)

### Next build session
`docs/NEXT_INSTANCE_BUILD_PLAN.md` + `docs/BUILD_PROGRESS.md` define the approved next-phase build: **63 dependency-ordered features** (all MVP + all fast-follow + all of accounting/job-cost/finance + warranty-registration + Delta progress sync + contract e-sign routing). Section 0 of the plan is a paste-ready kickoff prompt for a fresh instance. Access tokens for Railway/Vercel/Supabase live in `C:\Users\rjfla\.app-secrets.env` (Railway CLI authed, Vercel MCP connected, Supabase MCP scoped to the "Fred's Estimator" org only).

---

## Demo Logins (do not change until real staff are set up)
- `fred@trulineroofing.com` / `truline2024` → Super Admin
- `office@trulineroofing.com` / `office123` → Manager
- `fieldcrew@trulineroofing.com` / `roof123` → Field Crew

---

## Key Technical Notes

- **gpt-5.5 quirks:** Does not accept `temperature` or `max_tokens` — use `max_completion_tokens` only
- **Zapier webhook secret:** Available in Admin tab of live app (Copy button), also in `.env` as `ZAPIER_SECRET`
- **QuickBooks secret:** In `.env` as `QUICKBOOKS_SECRET` — will need to be entered in Zapier QB zap
- **PORT:** Railway sets this automatically from its environment — never hardcode or override
- **db.json:** JSON flat-file database, gitignored, lives on Railway's filesystem (ephemeral — see To-Do #7)
- **documents/ folder:** Also ephemeral on Railway — uploads survive until next deploy only

---

## Architecture Summary
- FastAPI + Uvicorn backend (`main.py`)
- Vanilla JS SPA frontend (`static/index.html`, `app.js`, `style.css`)
- JSON flat-file storage (`db.json`)
- All integrations via Zapier webhooks (no direct API calls to Roofr/QuickBooks)
- OpenAI used for chat (`/chat`) and voice transcription (`/transcribe`)
