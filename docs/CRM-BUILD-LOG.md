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

<!-- Append outcome (commit, deploy id, verify) below as the work completes. -->
