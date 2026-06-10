# TruAgent — Build Plan for the Next Instance

> **Purpose:** This is the single document a fresh Claude instance follows to build the feature set Fred approved. It contains (0) a paste-ready kickoff prompt, (1) current state, (2) hard rules, (3) architecture, (4) the target data model, (5) cross-cutting principles, (6) the **numbered master build list** (the tracker), and (7) a coverage map proving every requested feature is included. Source of truth for *what each feature does* is `docs/FEATURE_CATALOG.md`; this doc is *how and in what order to build them*.

---

## 0. KICKOFF PROMPT (Fred: paste this into the new instance)

> You are continuing the build of **TruAgent**, Truline Roofing's internal AI operations PWA (FastAPI `main.py` + vanilla-JS `static/` + JSON flat-file storage). Working copy: `C:\Users\rjfla\Documents\TruAgent`. It is **live** at https://truagent-production.up.railway.app (GitHub `DerfEflow/TruAgent`, auto-deploys on push to `main`) and now has **persistent storage** (Railway volume at `/data`, `DATA_DIR=/data`).
>
> **Read `docs/NEXT_INSTANCE_BUILD_PLAN.md` in full before doing anything**, then `docs/FEATURE_CATALOG.md`, `docs/MVP_GAP_ASSESSMENT.md`, `docs/handoff.md`, `main.py`, and `static/app.js`. Build the **numbered master list** in section 6 of the build plan, **in order**, one item at a time. Work autonomously — use best judgment, only stop on hard blocks (missing credentials, an irreversible/spend decision, or a product-design choice only Fred can make). For each item: implement → verify locally → commit → tick the checkbox in `docs/BUILD_PROGRESS.md` → move on. **Do NOT push to `main` without Fred's explicit per-push OK** (pushing auto-deploys to production). Keep replies essentials-only + a numbered next-step menu with a recommendation; Fred replies by number.
>
> Security (hard): work only in `C:\Users\rjfla\Documents\TruAgent`; never touch backups; never commit `.env`, `db.json`, or `documents/`; never spend money or expose credentials without explicit OK. Tokens for Railway/Vercel/Supabase live in `C:\Users\rjfla\.app-secrets.env` (read at runtime, never echo). Start by creating `docs/BUILD_PROGRESS.md` from section 6's checklist, then begin at item **F1**.

---

## 1. Current state (as of 2026-06-09)

- **Live & deployed** on Railway with persistent storage (`/data` volume + `DATA_DIR=/data`). Data now survives redeploys.
- **AI chat is already an agentic tool-calling loop** (`/chat`): it can `list_jobs`, `get_job`, `update_job_status`, `add_job_note` (both sync to Roofr when `ROOFR_WEBHOOK_URL` is set), `send_email`, `send_sms`, and `get_job_financials` / `company_financials_summary` (manager+ only, gated server-side). Extend this loop for new "agent can do X" features — don't rebuild it. Tool registry lives in `_TOOL_DEFS` / `tools_for_role` / `execute_agent_tool` in `main.py`.
- **Jobs tab has working update controls** (stage dropdown + add-note box → `/roofr/update`, which saves locally and syncs to Roofr best-effort).
- **Model is configurable**: `OPENAI_MODEL` (default `gpt-5.5`) with `OPENAI_FALLBACK_MODEL` fallback. The local `.env` has a **working `OPENAI_API_KEY`**, so AI is testable locally (but each call spends Fred's money — keep verification calls minimal).
- **Inbound Roofr Zaps live**: "Job Stage Changed" + "Lead Created". `ROOFR_WEBHOOK_URL` (outbound) is **not** set on prod yet, so Roofr-bound updates currently report "not configured" until Fred builds that Zap.
- **Specs corpus exists** (per Fred's memory): manufacturer coating specs already scraped for Alpha Estimator at `Documents/truline-estimator/specs/`. **Volume-solids %** and weather/cure limits should be sourced from there, not hardcoded.

## 2. Hard rules & how not to get lost

1. **Work only in** `C:\Users\rjfla\Documents\TruAgent`. Never touch backups. Never commit `.env`, `db.json`, `documents/`.
2. **Never push to `main` without Fred's explicit OK** — it auto-deploys to production. Commit freely; batch pushes and ask.
3. **One item at a time, in order.** Maintain `docs/BUILD_PROGRESS.md` (checkbox per item). After each item: implement → verify → commit (`git commit`, do not push) → tick the box.
4. **Verify before claiming done.** Backend logic: offline test via `TestClient` (no OpenAI spend where possible). AI behavior: a *minimal* real call. Note what you couldn't verify (e.g. Roofr round-trip needs prod).
5. **Reuse, don't rebuild.** The chat agent, `/roofr/update`, the webhook normalizer, and the `_op_*` helpers already exist. New "doors" (Alpha/Delta/Dominate) should mirror the `/quickbooks/webhook` + `/zapier/webhook` patterns (shared-secret, tolerant body parsing).
6. **Respect roles.** Field crew (`user`) never sees financials — gate at the data layer (tools + response shaping), not just the prompt.
7. **Keep prompts lean.** Don't dump the whole DB into the model; pass compact, step-scoped context + tools (the `/chat` endpoint already does this — follow that pattern).
8. **Stop only on hard blocks.** Missing API key/account, a spend decision, or a genuine product choice. Otherwise make a sensible default, note it, keep building.

## 3. Architecture & where things are

- `main.py` — FastAPI app: auth (JWT, 3 roles), routes, `load_db`/`save_db` (atomic writes), the agent operation helpers (`_op_update_job_status`, `_op_add_job_note`, `_op_send_email`, `_op_send_sms`, `_job_financials`, `_company_financials_summary`), the tool registry, and the agent loop (`_run_agent_loop` / `_create_completion`).
- `static/index.html`, `app.js`, `style.css` — the SPA (tabs: Chat, Jobs, Documents, Financials, Admin).
- Storage at `DATA_DIR` (`/data` on prod, project dir locally): `db.json` + `documents/`.
- Run locally: `.\.venv\Scripts\python.exe main.py` (port from `PORT`, default 5000).
- All third-party integrations go through **Zapier webhooks** (no direct vendor APIs). New inbound feeds = new secured webhook endpoints.

## 4. Target data model (lock these shapes early — section F0 below)

Extend `db.json` toward this shape so 60+ features share one schema instead of inventing their own. Add fields lazily but name them per this map:

```
jobs[job_id]:
  # existing: job_id, client_name, address, status, workflow_stage, notes[], invoices[], expenses[], + arbitrary Roofr fields
  budget:        { contract_value, system, substrate, sqft, est_gallons_by_product{}, dry_mil_target,
                   labor_hours_by_method{}, loaded_labor_rate, material_cost_per_gal{}, quoted_margin }   # from Alpha (F1)
  production_logs: [ { date, crew, product, gallons_applied, sqft_coated, wet_mil[], hours_by_type{}, weather{}, photos[], notes } ]  # from Delta (F2)
  coats:         [ { seq, product, applied_at, wet_mil, expected_dry_mil, inter_coat_window_hrs, cure_state } ]
  prep_signoff:  { items{}, signed_by, signed_at }
  qa:            { flags[], achieved_dry_mil, warranty_min_mil, status }
  schedule:      { phases[], assigned_crew, sprayer_id, material_needed_by }
  weather_status: { verdict, checked_at, reason }
  warranty:      { manufacturer, type, term_years, required_mil, install_date, registered, cert_number,
                   registration_deadline, renewal_recoat_due }       # registration (F-29) + renewal (F-35)
  change_orders: [ { id, reason, added_gallons, added_hours, price, approved_by, approved_at } ]
  billing:       { draws[], retainage_pct, retainage_held, ar_status }
  pipeline:      { stage, source, rep, first_touch_at, sla_due, loss_reason }
  timelogs:      [ { employee, arrive, depart, geo } ]

# new top-level maps:
financials:      { invoices{}, expenses{} }   # expenses enriched with product/gallons_purchased/$_per_gal/lot (F5)
parties:         { <id>: { type:'sub'|'vendor', name, coi{expiry,carrier,limits}, w9, subcontract, trade, cleared } }   # F47
weather_profiles:{ <system>: { temp_min,temp_max,surface_min,surface_max,rh_max,surface_minus_dewpoint,
                               rain_free_hrs_apply, min_cure_before_rain_hrs, inter_coat_window_hrs } }   # F6, seed from specs corpus
templates:       { <id>: { name, kind, body_with_merge_tokens } }   # F48
sds:             { <product>: { filename, filepath } }   # F50
employees:       { <id>: { name, certs:[{type,expiry}] } }   # F51
doc_chunks:      { <doc_id>: [ { text, embedding[], page } ] }   # F60 RAG
opportunities:   { <id>: { ...pipeline fields, linked job_id } }   # F30 (may reuse jobs)
```

**Three-bucket gallon model (never sum/conflate):** `est_gallons` (Alpha baseline) · `gallons_applied` (Delta logs) · `gallons_purchased` (QuickBooks). Applied-vs-estimated = margin leak signal; applied-vs-purchased = waste/theft signal.

**Achieved dry-mil** ≈ `gallons_applied × 1604 × volume_solids% ÷ sqft_coated`, where `volume_solids%` is **per product from the specs corpus** (silicones ~90–96%, acrylics ~45–55%). A single constant makes the number meaningless.

## 5. Cross-cutting principles

- **Scheduler is a hard dependency** for ~6 features (cadences, weather alerts, digests, COI/cert scans, renewal reminders). Build it once (F4). It is useless without persistent storage — which is now done.
- **Two inbound "doors" each light up 4 domains:** Alpha estimate import (F1) and Delta production log (F2). Build them early.
- **Weather profiles (F6) + volume-solids (in F1/specs) are seeds** consumed by reconciliation, scheduling, and RAG features.
- **Extend the existing chat agent** for every "AI can do/answer X" item (items 28, 37, 61) — add tools, don't fork the loop.

---

## 6. NUMBERED MASTER BUILD LIST (the tracker)

Build top-to-bottom. `[src]` = catalog section/tier it satisfies. `Done-when` = acceptance check. Copy this into `docs/BUILD_PROGRESS.md` as a checkbox list.

### PHASE F — Foundations (build first; each unblocks many)

- **F1. Inbound Alpha Estimator door — estimate baseline import.** `[Sec2 MVP + Sec3 MVP + Sec4 FF + Sec6 FF]` New secured webhook `POST /alpha/webhook` (mirror `/quickbooks/webhook`, `ALPHA_SECRET`). Writes the job `budget{}` block (contract value, est gallons/product, dry-mil target, sqft, substrate, labor hours by method, **loaded_labor_rate + material_cost_per_gal**, quoted margin). Revised estimates update in place (don't duplicate). **Done-when:** posting a sample estimate creates/updates a job with a populated `budget`, idempotent on re-post.
- **F2. Inbound Delta Coating Logistics door — daily production log ingest.** `[Sec1 MVP + Sec2 MVP + Sec4 Later "Delta progress sync"]` `POST /production/webhook` (`PRODUCTION_SECRET`) appends a `production_logs[]` entry (gallons applied by product, sqft coated, wet-mil readings, hours by type, weather, photo refs). **Done-when:** posting a log appends to the right job, advances `% complete`, and the applied-gallon bucket updates.
- **F3. Inbound Dominate lead door + lead intake normalizer/router.** `[Sec3 MVP + Sec6 FF]` `POST /leads/webhook` (`LEADS_SECRET`) + a normalizer that tags source/geo, dedupes by address+name, assigns a rep, stamps a first-touch SLA. Routes to jobs/opportunities (and optionally Roofr). **Done-when:** a posted lead becomes a deduped opportunity with source + SLA.
- **F4. Scheduler primitive.** `[cross-domain dependency]` A secured `POST /cron/tick?task=…` endpoint (driven by a Railway cron or a Zapier Schedule), dispatching to registered scheduled jobs. **Done-when:** hitting the endpoint runs a no-op task and logs it; ready for digests/scans to register.
- **F5. QuickBooks expense enrichment → coating material cost tracking by gallon.** `[Sec2 MVP]` Extend `/quickbooks/webhook` expense shape with product/manufacturer/**gallons_purchased**/$-per-gal/lot#; roll up purchased-vs-budgeted gallons; flag PO price drift. **Done-when:** an enriched expense updates the purchased-gallon bucket and a per-job material rollup.
- **F6. Per-coating-system weather rule profiles (+ weather source).** `[Sec4 MVP]` Admin-editable `weather_profiles{}` seeded from the specs corpus; columns incl. **post-application minimum-cure-before-rain hours** as a first-class field. Add a weather lookup (Zapier/weather API via webhook). **Done-when:** a job address + system yields a GREEN/YELLOW/RED verdict from real forecast vs profile.

### PHASE A — Accounting, Job Costing & Finance (ALL of Section 2)

- **A7. Per-job cost-category breakdown.** `[Sec2 MVP]` Bucket cost into burdened labor / material(gal) / equipment+solvent / prep / sub / other. **Done-when:** a job shows categorized costs, not one lump.
- **A8. Labor cost capture w/ 45% burden (from Delta).** `[Sec2 MVP, dep F2]` hours × loaded_rate × 1.45, split spray vs prep/roller, vs estimate. **Done-when:** Delta hours produce burdened labor cost + variance.
- **A9. Gallons applied vs. estimated tracker.** `[Sec1 MVP, dep F1+F2]` Running % of estimate consumed per product; flag crossing estimate before full coverage. **Done-when:** per-product applied/estimated % with over-run flag.
- **A10. Coverage-rate reconciliation → achieved dry-mil.** `[Sec1 MVP = Sec6 FF, dep F1+F2+F6/specs]` achieved dry-mil from gallons+sqft+volume-solids; compare to estimate AND spec minimum; flag too-thin (warranty) / too-thick (margin); reconcile vs wet-mil where present. **Done-when:** a job shows achieved vs required mil with correct per-product volume-solids.
- **A11. Margin alert vs. estimate.** `[Sec2 MVP, dep F4 for scheduled variant]` Fire when live margin drops >5 pts below quote or gallons/hours exceed budget; surface in finance tab + chat + optional email/SMS. **Done-when:** a sample over-budget job raises an alert.
- **A12. Company-wide profitability dashboard.** `[Sec2 MVP]` Backlog, billed-to-date, blended margin, sliced by system/substrate/crew/month. **Done-when:** dashboard renders cross-job rollups (manager+ only).
- **A13. WIP report (earned vs billed).** `[Sec2 FF]` % complete → earned revenue, billed-to-date, over/under-billing. **Done-when:** per-job WIP position computes.
- **A14. Progress billing w/ draw schedule & retainage.** `[Sec2 FF]` Deposit + milestone draws + retainage (≈10%); compute next due draw; push a QuickBooks invoice (net of retainage) via Zapier. **Done-when:** a draw schedule yields the next invoice amount.
- **A15. Change order tracking.** `[Sec2 FF]` Per-job CO log (added gallons/hours/price/approval); approved COs revise the baseline. **Done-when:** an approved CO updates `budget` + cost.
- **A16. AR aging & collections view.** `[Sec2 FF]` Bucket unpaid invoices 0-30/31-60/61-90/90+; one-click reminder via comms webhooks; retainage separate. **Done-when:** aging buckets + reminder action work.
- **A17. AP / vendor bill & PO tracking.** `[Sec2 Later — included]` Expenses grouped by vendor + due-date aging; optional PO capture + PO-to-bill matching. **Done-when:** vendor aging + PO match flag overruns.
- **A18. Payroll / time export.** `[Sec2 Later — included]` Aggregate Delta hours per employee per pay period (spray vs prep, per-job) → payroll CSV/webhook. **Done-when:** export produces a correct period CSV.
- **A19. Equipment & consumables cost allocation.** `[Sec2 Later — included]` Allocate spray-rig day-rate, tip/hose wear, solvent, fuel/mob to jobs. **Done-when:** spray cost lands on jobs, not overhead.
- **A20. Warranty-hold / retainage-release tracker.** `[Sec2 Later — included]` Gate final retainage-release invoice on warranty registered + final inspection + punch list cleared. **Done-when:** release invoice is blocked until gates pass.

### PHASE P — Production & QA (Sec 1 MVP + Fast-follow + the requested warranty-registration item)

- **P21. Dry-mil thickness log & QA checkpoint.** `[Sec1 MVP]` Crew logs wet-mil per coat per section; convert to expected dry-mil via volume-solids; auto-flag below warranty min. **Done-when:** readings store + flag low mil.
- **P22. Substrate prep sign-off checklist.** `[Sec1 MVP]` Per-area prep gate (clean/rust/seams/ponding/primer/seal) signed by crew lead; required items driven by substrate. **Done-when:** sign-off recorded + gates production start.
- **P23. Weather/dew-point application window check.** `[Sec1 MVP, dep F6]` Per application event record temp/surface/RH/dewpoint/wind vs window + **post-application rain-free hours achieved** vs min-cure-before-rain. **Done-when:** out-of-window apps flagged on the job.
- **P24. Job production dashboard & % complete.** `[Sec1 MVP]` Per-job rollup (sqft coated, gallons vs est, current coat, crew-days, weather, QA flags) + "production health" badge on the jobs list. **Done-when:** dashboard + badge render.
- **P25. Inter-coat recoat-window & cure-time tracker.** `[Sec1 FF = Sec4 Later]` Coats as ordered stages with `inter_coat_window` + cure intervals; warn on too-soon recoat / lapsed window. **Done-when:** next-coat window + lapse warning compute. *(Name it `inter_coat_window`, distinct from renewal cycle in P/S items.)*
- **P26. Photo documentation tied to job/area/stage.** `[Sec1 FF]` Photos tagged job+area+stage (before/prep/coat/after) + timestamp; per-job gallery. **Done-when:** upload, tag, and gallery work (uses `/data` storage).
- **P27. Punch list per job.** `[Sec1 FF]` Open items (touch-ups/thin spots/unsealed penetrations) w/ area/assignee/photo/status; auto-seeded from failed QA. **Done-when:** punch items CRUD + QA seeding.
- **P28. AI production assistant (field-data Q&A).** `[Sec1 FF, extend chat]` New tools so chat answers "which jobs are over estimated gallons / had out-of-window apps / missing mil readings." Field role stays financial-blind. **Done-when:** chat answers from production data via tools.
- **P29. Manufacturer warranty registration tracker.** `[Sec1 Later — REQUESTED]` Capture system/warranty type/required mil/deadline; pre-flight documentation completeness before submission; store returned warranty number. **Done-when:** a job shows "registration pending" → "registered #" with deadline alerting. *(Shares the `warranty{}` block with O49/S35.)*

### PHASE S — Sales, Estimating Pipeline & CRM (Sec 3 MVP + Fast-follow)

- **S30. Unified sales pipeline (Kanban by coating stage).** `[Sec3 MVP]` Stages New Lead → Site Survey → Measured/Cores → Estimating → Proposal → Negotiation → Won/Lost; drag-to-advance pushes stage to Roofr via existing outbound webhook. **Done-when:** board renders + stage change persists & syncs.
- **S31. Follow-up cadence engine.** `[Sec3 MVP, dep F4]` Per-stage reminders (e.g. "no contact 48h after Proposal Sent", "weather-postponed → rebook"); weather-aware templates. **Done-when:** a due cadence step fires via the scheduler.
- **S32. Win/Loss tracking w/ coating loss reasons.** `[Sec3 MVP]` Structured loss reasons (price/tear-off/competitor system/substrate saturated/warranty short/weather); win-rate by source/rep/substrate/system. **Done-when:** loss capture + win-rate rollups.
- **S33. Proposal e-sign / acceptance capture.** `[Sec3 FF — pairs with O57]` Send Alpha proposal for signature; acceptance flips stage to Won, attaches PDF, fires production/procurement handoff. **Done-when:** signed event → Won + attached PDF.
- **S34. Referral & online-review capture.** `[Sec3 FF]` On completion, queue a review-ask timed to post-cure; capture referrals as source-tagged leads (loops to Dominate via F3). **Done-when:** completion schedules a review-ask; referral creates a lead.
- **S35. Renewal / re-coat maintenance engine.** `[Sec3 FF]` Store warranty term + install date + achieved mil → compute `renewal_recoat_due`; surface "due for re-coat" warm leads with original scope pre-filled. **The recurring-revenue flywheel.** **Done-when:** renewal-due list populates with pre-filled scope. *(`renewal_recoat_cycle`, distinct from P25 inter-coat window.)*
- **S36. Territory & rep performance dashboard.** `[Sec3 FF]` Per-rep/territory: leads, SLA hit rate, win rate, gallons sold, value, margin (money columns manager+ only). **Done-when:** dashboard renders with role-gated money.
- **S37. AI pipeline copilot.** `[Sec3 FF, extend chat]` Tools to query by gallons/system/renewal-due, advance stages, log win/loss, draft cadence emails. **Done-when:** chat performs pipeline actions via tools.
- **S38. Opportunity timeline & comm log.** `[Sec3 FF = overlaps O54]` One activity feed per opportunity: emails/SMS, stage changes, estimate revisions, signed events, survey notes. **Done-when:** unified per-opportunity timeline renders.

### PHASE C — Scheduling, Dispatch & Crew (Sec 4 MVP + Fast-follow; "Delta progress sync" satisfied via F2)

- **C39. Crew calendar & job scheduling board.** `[Sec4 MVP]` Drag-drop day/week board assigning jobs to crews/dates; multi-day blocks colored by stage. **Done-when:** assignments persist + render on a week board.
- **C40. Weather-aware application window flags.** `[Sec4 MVP = Sec6 FF "go/no-go", dep F4+F6]` Morning forecast per job vs per-system limits → GREEN/YELLOW/RED, checking application-time AND post-application rain-free window. **Done-when:** each scheduled job shows a daily verdict; same-day SMS optional.
- **C41. Multi-day coating sequence templates.** `[Sec4 FF]` Job = ordered phases with cure gaps; calendar auto-lays phases, inserts inter-coat windows, skips RED days. **Done-when:** a template expands into dated phases.
- **C42. Equipment & sprayer assignment.** `[Sec4 FF]` Registry of rigs/tips/lifts assignable per job/day; hard-block double-booking the spray rig. **Done-when:** double-booking the rig is rejected.
- **C43. Material staging & delivery coordination.** `[Sec4 FF]` Compute required gallons, set material-needed-by tied to first coat, flag un-staged jobs N days out. **Done-when:** staging flags surface on the board.
- **C44. Daily dispatch sheet (night-before auto-send).** `[Sec4 FF, dep F4+comms]` Per-crew tomorrow sheet (address, access, system+target mil, gallons staged, weather verdict, phase) via email/SMS. Field-safe (no pricing). **Done-when:** scheduler sends a correct per-crew sheet.
- **C45. Crew time & location check-in.** `[Sec4 FF, feeds A8]` Tap Arrive/Depart + timestamp + optional geo → `timelogs`; feeds labor cost. **Done-when:** check-ins create timelogs consumed by A8.

### PHASE O — Office Admin, Compliance & Safety (Sec 5 MVP + Fast-follow; persistent storage already DONE; + requested e-sign routing)

- **O46. COI registry & expiry tracking (company + subs).** `[Sec5 MVP, dep F4]` Store COIs (carrier/limits/expiry); daily scan flags 30/14/0-day. **Done-when:** expiring COIs surface via the scheduler.
- **O47. Subcontractor / vendor compliance profiles.** `[Sec5 MVP]` `parties` record per sub/vendor (COI, W-9, subcontract, trade) + green/yellow/red "cleared to work" rollup. **Done-when:** a party's cleared status computes from its docs.
- **O48. Document template library + mail-merge.** `[Sec5 MVP]` Reusable subcontract/proposal/warranty/lien-waiver templates with merge tokens (`{{coating_system}}`, `{{dry_mil_spec}}`, `{{warranty_years}}`). **Done-when:** a template merges job data into output.
- **O49. Manufacturer warranty document registry.** `[Sec5 MVP, pairs P29]` Per-job warranty record tying cert to as-applied system + dry-mil + lots; "registration pending" until cert on file. **Done-when:** warranty doc state tracked per job.
- **O50. SDS library for coatings & solvents.** `[Sec5 MVP]` Phone-accessible SDS by product (coatings/primers/xylene/MEK). OSHA HazCom. **Done-when:** SDS searchable + viewable on mobile.
- **O51. Employee certification & training tracker.** `[Sec5 MVP, dep F4]` Per-employee OSHA/fall-protection/respirator fit-test/lift/applicator certs w/ expiry alerts. **Done-when:** lapsing certs alert via scheduler.
- **O52. Compliance dashboard with AI Q&A.** `[Sec5 MVP, extend chat]` One tab rolling up everything expiring/missing; chat answers "which subs can't work next week?" **Done-when:** dashboard + chat answer from compliance data.
- **O53. Lien waiver generation & tracking.** `[Sec5 FF]` Generate conditional/unconditional progress/final waivers from job+payment data; track sent→signed→received per job/sub. **Done-when:** waiver generated + status tracked.
- **O54. Customer communication log.** `[Sec5 FF = overlaps S38]` Auto-captured per-job timeline of every email/SMS + logged calls/visits. **Done-when:** comms auto-log to the job timeline.
- **O55. Permit tracker.** `[Sec5 FF]` Per-job permit records + status gate (can't mark ready-to-start without issued permit where required). **Done-when:** permit gate enforced.
- **O56. Job safety / pre-task plan (JHA).** `[Sec5 FF]` Coating-specific JHA (fall protection, respirator/solvent, silica, overspray/wind) auto-filled from the job's system; daily crew sign-off. **Done-when:** JHA generates + crew signs.
- **O57. Contract / proposal e-signature routing.** `[Sec5 Later — REQUESTED, pairs S33]` Route proposals/subcontracts/warranties for e-sign; track sent→viewed→signed; file executed PDF on the job. **Done-when:** a document routes for signature and the signed PDF lands on the job. *(May use DocuSign or a Zapier e-sign step.)*

### PHASE I — AI, Voice & Mobile-First Field UX (Sec 6 MVP + Fast-follow)

- **I58. Structured voice field report.** `[Sec6 MVP, dep F2 schema]` Existing `/transcribe` (Whisper) → an extraction call turns the transcript into a typed object (job, gallons, product, wet-mil, sqft, prep, weather, hours) → writes a `production_log` with a confirm card. **Done-when:** a spoken report becomes a structured, user-confirmed production log.
- **I59. Morning ops digest (role-scoped).** `[Sec6 MVP, dep F4]` Daily push per role: stalled jobs, gallons-over-estimate, past-due invoices, unscheduled approved jobs (mgr); today's addresses+system+target mil+weather (crew). **Done-when:** scheduler sends correct role-scoped digests.
- **I60. Document RAG over specs/SDS/warranties/contracts.** `[Sec6 MVP]` On upload, parse + embed; chat answers "what's the inter-coat window / volume-solids for the Gaco silicone?" **with a citation**. **Done-when:** chat answers a doc-content question with a source citation. *(Feeds A10's volume-solids.)*
- **I61. Natural-language job report.** `[Sec6 MVP, extend chat]` "How did we do on Acme?" → stage, gallons vs est, mil compliance, days on site, money (manager+ only), open issues, next action. **Done-when:** chat returns a role-correct job summary.
- **I62. Job-over-budget & stalled-job anomaly detection.** `[Sec6 FF, dep F4]` Scheduled scan flags margin under floor, jobs with no log/expense in N days, past-due invoices, approved-no-start → digest line + "Needs Attention" badge. **Done-when:** scan produces flags + badges.
- **I63. Mobile-first field mode.** `[Sec6 FF]` Crew view: oversized voice button, big tappable job cards (address+system+target mil+weather), photo capture, offline queue; no financial UI for this role. **Done-when:** a crew login gets the field-optimized, financial-free view.

---

## 7. Coverage map (every requested catalog feature → build item)

**All MVP:** Sec1 → F2,A9,A10,P21,P22,P23,P24 · Sec2 → F1,F5,A8,A7,A11,A12 · Sec3 → S30,F3,S31,F1,S32 · Sec4 → C39,C40,F6 · Sec5 → O46,O47,O48,O49,O50,O51,O52 · Sec6 → I58,I59,I60,I61,(storage ✅done).
**All Fast-follow:** Sec1 → P25,P26,P27,P28 · Sec2 → A13,A14,A15,A16 · Sec3 → S33,S34,S35,S36,S37,S38 · Sec4 → F1(est-intake),C41,C42,C43,C44,C45 · Sec5 → (storage ✅done),O53,O54,O55,O56 · Sec6 → C40(go/no-go),A10(reconciliation),I62,I63,F1/F3(sibling intake).
**All of Section 2 incl. Later:** A17,A18,A19,A20 (the Later items) + all Sec2 MVP/FF above.
**Requested Later items:** Manufacturer warranty registration tracker → **P29**; Delta progress sync → **F2** (+ surfaced in C40/P24); Contract/proposal e-signature routing → **O57**.

*Deliberately excluded (not requested):* Sec1 Later (Final QA sign-off packet, Rework/callback); Sec3 Later (quote-expiry watchlist, proposal versioning, sales→production handoff); Sec4 Later (weather auto-reschedule, sub coordination, readiness pre-flight, seasonal capacity); Sec5 Later (insurance audit export); Sec6 Later (AI photo defect tagging, separate warranty/renewal reminder tracker, AI closeout comms). If Fred wants any later, append them.

## 8. Per-item protocol & deploy

For **each** numbered item: (1) implement in a focused change; (2) verify — backend via `TestClient` offline where possible, AI via a minimal real call, note anything only provable on prod; (3) `git commit` (do **not** push); (4) tick the box in `docs/BUILD_PROGRESS.md`; (5) next item. **Batch a push only when Fred says so** — it auto-deploys and (now that storage is persistent) is safe but still production. New webhook secrets (`ALPHA_SECRET`, `PRODUCTION_SECRET`, `LEADS_SECRET`) and any API keys (weather, e-sign) go in Railway Variables + local `.env`, never committed.

## 9. Definition of done (whole engagement)

Every item in section 6 implemented, verified, committed, and ticked in `docs/BUILD_PROGRESS.md`; the app boots and runs without errors; the three sibling-app inbound doors (F1/F2/F3) accept and reconcile data on the three-bucket gallon model; the chat agent answers production/finance/scheduling/compliance questions with correct role-gating; and Fred has authorized the production deploy(s).
