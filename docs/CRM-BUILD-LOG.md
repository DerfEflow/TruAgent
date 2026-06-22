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

**Next session — pick up at P1-2 (Win/Loss UI + analytics surfacing).** The backend
(`POST /pipeline/{id}/win-loss`, `GET /sales/win-loss` with `by_loss_reason`/`by_rep`) already exists and
is unwired; add: a Won/Lost control on each kanban card (loss-reason dropdown) and render the rollups
in the pipeline summary. Then P1-3 (cadence engine + cron), etc. per `CRM-ROADMAP.md` §4.

