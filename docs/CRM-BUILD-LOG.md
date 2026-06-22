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

**Next session — Phase 2.** Start at **P2-9 (customer/contact entity)** or **P2-10 (unified comms inbox**,
the biggest day-to-day gap; also needs the EMAIL_/SMS inbound door + Fred connecting Gmail/Twilio). See §5.

