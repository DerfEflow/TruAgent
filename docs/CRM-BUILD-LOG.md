# TruAgent CRM — Build Log

Running notes, newest at the bottom. Companion to `CRM-ROADMAP.md`. Each entry: date,
what changed, files, deploy/verify result, and where to pick up next.

---

## 2026-06-22 — Roadmap created; Phase 1 started

**Context set this session (before Phase 1):**
- Postgres migration done (`app_state` JSONB via Supabase REST) — TruAgent is off `db.json`.
- App launcher shipped — "Apps" landing tab with cards to Alpha / Delta / dashboard (commit 66e1570).
- Full CRM code audit done → finding: CRM is a broad backend skeleton with a thin UI; ~half the
  endpoints have no frontend; `opportunities` and `jobs` are never linked. Plan written in
  `CRM-ROADMAP.md` + the F:\ brief.

**P1-1 — Opportunity ↔ Job link + convert-to-job:** *(in progress this entry)*
- Branch: `crm-phase1` (off `main` 66e1570).
- Plan: add `ConvertToJobRequest` model + `POST /pipeline/{opportunity_id}/convert` (manager+),
  idempotent, sets `opp.job_id` ↔ `job.origin_opportunity_id`; create a TruAgent-native job
  `opp-<id>` or link an explicit `link_job_id`. UI: "Convert to Job" button on pipeline cards.
- Why first: nothing sets `opp.job_id` today, so the Won-stage→job sync and e-sign auto-Won are
  dead branches. This is the keystone that revives them.

**P1-1 outcome — DONE.**
- Shipped: `ConvertToJobRequest` model + `POST /pipeline/{opportunity_id}/convert` (manager+);
  `/pipeline` now returns `job_id` per opp; "Convert to Job" button on kanban cards (`app.js convertOpp`).
- Job id scheme for opp-native jobs: `opp-<opportunity_id>`; bidirectional link `opp.job_id` ↔
  `job.origin_opportunity_id`. Idempotent re-convert. Optional `link_job_id` to attach an existing job.
- Verified locally (TestClient, isolated file-mode DB): lead→convert(created)→re-convert(idempotent)→
  pipeline shows job_id→job has origin_opp→**set Won propagates to job (keystone handoff works)**→field crew 403.
- Commit `50bc569` → pushed to `main` → Railway auto-deploy. Live verify: app 200 + convert route registered.

---

## 2026-06-22 (cont.) — Phase 1 completed (P1-2 … P1-8)

Rolled out the rest of Phase 1 in two batches (backend, then frontend) on branch `crm-phase1`.

**Backend (main.py):**
- P1-3 cadence engine: `ContactLogRequest.due_at`; `set_cadence` now sets `opp.next_followup_due`
  (default +3d). New cron `pipeline_alerts` (every 6h) → `db.pipeline_alerts` {overdue_followups, sla_breaches}.
- P1-5 lead SLA: folded into `pipeline_alerts` (past `sla_due`, still New Lead, never contacted).
- P1-4 review-flush: new cron `review_flush` (daily) drains queued review-asks past `send_after` via
  the email outbox (dormant-safe). Referral capture: `POST /job/{id}/referral` (+ `ReferralRequest`).
- P1-6 territory: `LeadWebhook.territory` stored on opps; `/sales/performance` now returns `by_territory`
  alongside `by_rep`.
- New reader `GET /sales/alerts` (manager+). New cron tasks registered in `_CRON_TASKS` + `_SCHEDULE`.

**Frontend (app.js — pipeline tab rebuilt):**
- P1-7 real **drag-and-drop kanban** (HTML5 dnd → `/pipeline/{id}/stage`).
- P1-2 **Won/Lost** buttons per card (`markOutcome`, loss-reason prompt) + **analytics tables** rendered
  (rep, territory, loss-reasons) — previously computed and discarded.
- P1-3/P1-5 **alerts banner** + summary counts from `/sales/alerts`.
- P1-8 **opportunity detail modal** (`openOppDetail`): timeline + cadence + a "log follow-up" form
  (writes cadence due dates). Convert-to-Job + "Job linked" retained from P1-1.

**Verified:** TestClient backend suite — cadence due→next_followup_due; pipeline_alerts (overdue+SLA);
review_flush→outbox+marked sent; referral stored; territory rollup; win/loss by_loss_reason; field-crew 403.
JS `node --check` clean; Python `py_compile` clean.

**Phase 1 = DONE.** Connections still Fred-gated before some of this *sends* externally: EMAIL_/SMS
webhooks (cadence/review actually emailing), QuickBooks Zaps. See `CRM-ROADMAP.md` §3.

---

## 2026-06-22 (cont.) — P2-10 unified comms inbox DONE

- Backend: `INBOX_SECRET` door; `db.messages` store; helpers `_thread_key` (email lc / phone last-10,
  channel-prefixed) + `_match_contact` (links a message to a job/opp by customer email/phone) +
  `_record_message`. Endpoints: `POST /inbox/webhook` (inbound, secret), `POST /inbox/send` (manager+,
  via dormant-safe email/SMS dispatch), `GET /inbox` (threads + unread), `GET /inbox/thread?key=`,
  `POST /inbox/thread/read?key=`. Models `InboxWebhook` / `InboxSend`.
- Frontend: "Inbox" tab (manager-only) — thread list (unread badges) + thread view (bubbles) + reply box.
- Verified (TestClient): inbound email auto-links job; bad secret 403; outbound queues; threads + unread;
  thread view; mark-read; field-crew 403; SMS inbound links opp by normalized phone. node --check + py_compile clean.
- **Fred-gated to go live:** set `INBOX_SECRET` + `EMAIL_WEBHOOK_URL` + `SMS_WEBHOOK_URL` on Railway, and wire
  a Zapier email-parser (→ /inbox/webhook channel=email) + Twilio inbound-SMS (→ channel=sms). Until then the
  inbox UI works and shows threads but nothing flows in/out automatically.

---

## 2026-06-22 (cont.) — Phase 2 COMPLETE (P2-9, P2-11, P2-12, P2-13)

- **P2-9 customer/contact entity:** `db.customers` + `CustomerRequest`; `POST/GET /customers`,
  `GET /customer/{id}` (360 view: links jobs/opps/threads by matching emails/phones via `_thread_key`),
  `PUT /customer/{id}`. UI: "Customers" tab (manager-only) — list + add form + 360 modal.
- **P2-11 material ordering:** `POST /job/{id}/material-order` builds line items from `budget.est_gallons`
  + waste_pct + manual extras, optional dormant-safe email to supplier; `GET /job/{id}/material-orders`.
  UI: "Material order" button per job in the customer 360 modal. (`MaterialOrderRequest`)
- **P2-12 stage-change automation:** `advance_opp_stage` now auto-sets `next_followup_due` per
  `_STAGE_FOLLOWUP_DAYS` on entering an active stage (drives the cadence engine + pipeline_alerts);
  Won/Lost clear it. No new UI (surfaces in alerts + detail).
- **P2-13 source/ROI:** `GET /sales/source-roi` (by_source leads/won/lost/win-rate/revenue); rendered
  as a "Lead Source ROI" table in the pipeline analytics.
- Verified (TestClient): customer 360 link by email; material order waste math (100→110, 20→22);
  stage→Proposal auto-schedules follow-up, Won clears it; source-roi rollup; field-crew 403.
  node --check + py_compile clean. **Note:** inbox door is fail-closed in prod (INBOX_SECRET unset →
  `_door_secret` returns an unguessable value) — correct/secure; Fred sets INBOX_SECRET to enable.

**Phase 2 = DONE.** Remaining roadmap = **Phase 3**: P3-14 1ESX measurements (needs ESX_API_KEY + account),
P3-15 Stripe payments, P3-16 customer portal.

---

## 2026-06-22 (cont.) — P3-15 Stripe payments DONE

- Truline Stripe account confirmed: wallet `TRUAGENT_STRIPE_KEY` = `sk_live` for **"Trulineroofing"**
  (NOT the Delta Log `STRIPE_SECRET_KEY` — that one is Delta's; do not use it for Truline).
- Backend: `STRIPE_API_KEY` + `STRIPE_WEBHOOK_SECRET` env; `POST /job/{id}/payment-link` (Checkout
  Session, ad-hoc amount, metadata.job_id), `GET /job/{id}/payments`, `POST /stripe/webhook`
  (HMAC-SHA256 verified) → marks job payment paid + records a `source:stripe` paid invoice in financials.
  `static/thanks.html` is the customer success page. `_stripe_post` helper (form-encoded, basic-auth key).
- Frontend: "Request payment" button per job in the customer 360 modal (`requestPayment`).
- Verified LIVE against the Truline account (TestClient): created a real `cs_live` Checkout link (no charge),
  expired the test session to clean up; signed webhook marks paid + adds invoice; bad sig 403; field-crew 403.
- Wiring: set `STRIPE_API_KEY` (from `TRUAGENT_STRIPE_KEY`) on Railway; registered a Stripe webhook
  endpoint → set `STRIPE_WEBHOOK_SECRET`. Customer pays on Stripe's hosted page via the emailed link —
  TruAgent stays internal.

**Remaining Phase 3:** P3-14 1ESX (needs ESX account/API key), P3-16 customer portal (decide if wanted),
proposals-polish doc. **2a still pending Fred:** approve Gmail+Twilio OAuth links so email/SMS send live.

---

## 2026-06-28 — P3-14 DIY roof-measurement estimator DONE (branch `crm-phase3`)

Fred chose **DIY over paid 1ESX**. Built the aerial building-footprint / roof-area estimator from
`aerial_building_footprint_roof_area_estimator_build_spec.md` (now committed). Geometry holds the
tape measure; AI only verifies.

**Pipeline:** address (or lat/lon, or pulled from a job/opp) → geocode (`_geocode`, Nominatim,
keyless) → open building footprints (`_overpass_buildings`, OSM/Overpass, **keyless**, with mirror
failover across 4 endpoints because the main one 504s constantly) → local tangent-plane
equal-area projection (`_project_xy`, sub-0.1% at building scale, no geo stack needed) → shoelace
area + perimeter + bbox dims (`_measure_geometry`, holes subtract, multipolygon-aware) → candidate
ranking + 0–100 confidence (`_score_candidate`: source priority + point-in-footprint + size
reasonableness) → roof-area estimate (`_roof_estimate`: footprint × slope_factor, + waste %) →
warnings + disclaimer. Human-correctable outline + AI **verify-only** (`_ai_measurement_review`:
reviews metadata, never imagery, never claims to measure; returns advisory JSON).

**Backend (main.py):** new constants (`OVERPASS_API_URL`+mirrors, `GOOGLE_SOLAR_API_KEY`,
`MS_FOOTPRINTS_URL`, slope/waste defaults, unit consts, `import math`). Models `MeasureRequest`/
`MeasureOptions`/`SelectCandidateRequest`/`ManualGeometryRequest`/`MeasurementToAlphaRequest`.
`db["measurements"]` added to `_normalize_db`. Endpoints (all `Depends(get_manager_or_above)`):
`POST /measurements/estimate`, `GET /measurements`, `GET /measurement/{id}`,
`POST /measurement/{id}/select-candidate` · `/manual` · `/ai-review` · `/to-alpha`. `_to-alpha`
writes the **same `budget` shape Alpha sends to `/alpha/webhook`** (`sqft`=roof area, footprint,
perimeter, source markers) onto a linked/created job. `_create_completion` gained a `**extra`
passthrough so the AI review can request `response_format=json_object`.

**Frontend:** "Measure" tab (manager-only) — address/job + radius/slope/waste/AI/solar controls →
result card (roof area, footprint, material area, perimeter, dims, source link, confidence badge,
warnings, AI advisory, OSM + Google-Maps verify links), multi-candidate picker, manual-correction
GeoJSON editor, "Pre-fill Alpha baseline" button, recent-measurements list.

**Sources:** OSM/Overpass + Nominatim are keyless (primary). Paid/keyed sources are **dormant-safe**:
`_google_solar_roof_area` (Fred-gated `GOOGLE_SOLAR_API_KEY`) and `_ms_footprints` (Fred-gated
`MS_FOOTPRINTS_URL`) both return None/[] + a warning when unset — they never break the estimate.
County-GIS connector slots into the ladder next when wanted.

**Verified:** `py_compile` + `node --check` clean. 30 in-process TestClient checks against an
isolated file-mode DB (pure geometry: 100×50 m rect → 5000 m²/300 m perimeter, hole subtraction,
point-in-poly, scoring; endpoints: offline→manual_required, manual→estimated+roof_estimate,
to-alpha writes budget.sqft, select-candidate, AI review advisory disclaimer; **field crew 403 on
estimate/list/get/ai-review/to-alpha**). **Live** end-to-end (network): Empire State Bldg →
Nominatim geocode + Overpass mirror failover → auto-selected way/34633854 at 82,987 sqft (~1% of
the true ~83,800 sqft), 13 candidates → selection-recommended + multi-building warning.

**Fred-gated (optional, none block the feature):** `GOOGLE_SOLAR_API_KEY`, `MS_FOOTPRINTS_URL`,
paid 1ESX (only if survey-grade wanted alongside DIY). **Future polish:** in-app Leaflet map draw
editor (today manual correction is a GeoJSON textarea + external OSM/Maps verify links); county-GIS
connector.

