# TruAgent — Roadmap

Built from reading the actual code (2026-06-07). Ordered biggest-unblock-for-
least-effort first.

## Current-state assessment

TruAgent is a **working, fairly complete app**, not a skeleton. It has login with
three role levels, an AI chat tab, a jobs tab, a documents tab (upload/download/
delete), a manager-only financials tab, and a super-admin tab (Zapier webhook
info + user management). The front end is a clean single-page PWA.

**What works**
- Boots cleanly and serves the web app locally.
- All three demo logins work and land on the right role-gated screens.
- Role permissions are enforced on the backend (field crew is blocked from
  user-management and financials; AI is told to hide money from field crew).
- Documents, jobs, users, and financial calculations are all implemented.

**What was broken (now fixed — Phase 0)**
- App crashed on start with no OpenAI key. Fixed (AI now dormant + friendly).
- No way to configure settings locally. Fixed (`.env` support added).
- Port was hard-coded. Fixed (adjustable via `PORT`).

**What's deliberately OFF (needs Fred's keys later — not bugs)**
- OpenAI chat, Roofr sync, QuickBooks finance feed, email, and SMS. All show a
  graceful "not configured" state until their settings are filled in.

**Minor polish remaining (Phase 1)**
- Jobs tab could render badly once real jobs sync in (two small display bugs).

## Phase 0 — Run locally, boot clean (DONE)
- [x] Create working copy from backup; set up git-safe workflow.
- [x] Decouple from Replit: venv + dependencies, `.env` loader, adjustable port.
- [x] Fix the no-API-key boot crash; AI dormant + friendly message.
- [x] Confirm it runs: all 3 logins, role gating, dormant integrations, errors.
- [x] Context hygiene (`.claude/settings.json`), docs, ROADMAP, DECISIONS.

## Phase 1 — Correctness polish (small, safe)
- [ ] Jobs tab: guard against a job with no `status` (avoids a render crash).
- [ ] Jobs tab: render note text properly (notes can be objects, not strings).
- [ ] Re-test the Jobs tab with a sample synced job.

## Phase 2 — Review-readiness niceties (optional, only if time)
- [ ] Light "demo mode" hint somewhere so reviewers know integrations are off.
- [ ] Confirm branding is consistently "Truline Roofing" across all screens.

## Pre-launch tasks (NOT now — these need Fred / cost money / go live)
- [ ] Replace the three demo passwords with real ones; set a real
      `SESSION_SECRET` on the host.
- [ ] Add the real `OPENAI_API_KEY` to turn on the AI assistant.
- [ ] Create the Zapier webhooks and fill in `ROOFR_WEBHOOK_URL`,
      `EMAIL_WEBHOOK_URL`, `SMS_WEBHOOK_URL`, plus the matching secrets.
- [ ] Deploy to a host (e.g. Railway). **Important:** `db.json` and the
      `documents/` folder must sit on a *persistent volume*, or all data resets
      on every deploy.
