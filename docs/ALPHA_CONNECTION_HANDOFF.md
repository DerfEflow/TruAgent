# Alpha Estimator → TruAgent connection — handoff for the next instance

> **Purpose:** Wire Alpha Estimator so a finished estimate lands in TruAgent as a budget baseline. The **receiving door is already live and verified in production**; the work left is the **sending side** (in the Alpha Estimator app) plus a few design decisions captured below. This doc is written so a fresh Claude instance can start strong without re-deriving the context.

_Last updated: 2026-06-13. (Written after the 2026-06-10 TruAgent QA sweep + production deploy; paths updated for the Business App Suite reorg — TruAgent now lives at `Documents/Business App Suite/TruAgent`, Alpha at `Documents/Business App Suite/Alpha Estimator`.)_

---

## 0. PASTE-READY KICKOFF PROMPT (Fred: paste into the new instance)

> You are wiring **Alpha Estimator → TruAgent**. TruAgent is Truline Roofing's internal ops PWA at `C:\Users\rjfla\Documents\Business App Suite\TruAgent`, **live** at https://truagent-production.up.railway.app (GitHub `DerfEflow/TruAgent`, auto-deploys on push to `main` — pushing needs Fred's explicit per-push OK). Alpha Estimator is Fred's roof-coating SaaS at `C:\Users\rjfla\Documents\Business App Suite\Alpha Estimator` (Supabase + Vercel, prod at alphaestimator.com).
>
> **The receiving door already exists and works in prod:** `POST /alpha/webhook`, authenticated by `ALPHA_SECRET` in the JSON body. `ALPHA_SECRET` is already set in TruAgent's local `.env` AND in Railway Variables (active — verified the old default is now rejected). Your job is the **sending side**: add an optional, configurable "Send to TruAgent" outbound module to Alpha that POSTs an estimate's budget baseline to that door when an estimate is finalized/accepted. **Read `TruAgent/docs/ALPHA_CONNECTION_HANDOFF.md` (this file) and `TruAgent/docs/APP_INTEGRATION_ROADMAP.md` first**, then decide the open questions in §3 with Fred before coding.
>
> Hard rules: work only in the relevant project dir; never commit `.env`/secrets; the `ALPHA_SECRET` value is read at runtime from TruAgent's `.env` or Railway — never echo it. Keep the three-bucket gallon model intact (Alpha owns *estimated*; never sum/overwrite buckets). Verify before claiming done (TestClient offline where possible; a single guarded prod probe with cleanup, or test against a local TruAgent on an isolated `DATA_DIR`). Report essentials + a numbered next-step menu; Fred replies by number.

---

## 1. Current state (what's done)

- **TruAgent is fully deployed and stable** (QA sweep 2026-06-10: 31 bugs fixed, verified, pushed; further leads/digest/email refinements landed on top through ~06-13). The Alpha door is part of that deploy.
- **`POST /alpha/webhook` is LIVE** and idempotent. Posting an estimate creates/updates a job and writes its `budget{}` block; re-posting the same `job_id` updates in place (no duplicate).
- **`ALPHA_SECRET` is provisioned**: local `TruAgent/.env` + Railway Variables (set with `--skip-deploys`, activated by the 2026-06-10 deploy). The pre-existing default `"change_alpha_secret_in_production"` is now **rejected (403)** in prod — confirmed.
- **What is NOT done:** Alpha emits nothing yet. There is no outbound call from Alpha to TruAgent. That's the whole remaining task.

## 2. The door's exact contract (`POST /alpha/webhook`)

Body is JSON. `secret` and `job_id` are required; everything else optional. Source: `AlphaWebhook` model + `alpha_webhook()` in `TruAgent/main.py`. **Re-verify the model in the current `main.py` before coding — the codebase kept evolving after this was written.**

```jsonc
{
  "secret": "<ALPHA_SECRET>",          // required; body auth
  "job_id": "<stable id>",             // required; the key the job is stored under
  "client_name": "Acme Warehouse",
  "address": "123 Main St",
  "contract_value": 100000,            // → budget.contract_value (MONEY)
  "coating_system": "silicone",        // → budget.system + job.coating_system
  "substrate": "metal",                // → budget.substrate
  "sqft": 20000,                       // → budget.sqft
  "dry_mil_target": 20,                // → budget.dry_mil_target
  "quoted_margin": 45,                 // → budget.quoted_margin (MONEY)
  "loaded_labor_rate": 55,             // → budget.loaded_labor_rate (MONEY; see §3.3)
  "est_gallons": { "GacoRoof": 400 },              // → budget.est_gallons  (ESTIMATED bucket)
  "material_cost_per_gal": { "GacoRoof": 45 },     // → budget.material_cost_per_gal (MONEY)
  "labor_hours_by_method": { "spray": 120 },       // → budget.labor_hours_by_method
  "data": { /* any extra fields, merged onto the job */ }
}
```

Behavior: validates `secret` → `403` on mismatch; `setdefault` the job by `job_id`; writes the `budget{}` sub-object; stamps `budget.imported_at`; returns `{status, job_id, budget_fields}`. **Idempotent** — re-posting updates in place.

These budget fields are the **"estimated" side** that Delta production logs and QuickBooks expenses are reconciled against (features A8–A11, A10 coverage, margin alerts). `loaded_labor_rate` + `material_cost_per_gal` are the **only** costing multipliers TruAgent has — it owns no rate table — so they MUST come in on this baseline (or downstream costing has nothing to multiply).

## 3. OPEN DECISIONS — settle these with Fred before coding

### 3.1 `job_id` convention (collision risk) — **decide first**
The built door stores under whatever `job_id` you send. A Roofr-synced job and an Alpha estimate must not collide. The roadmap's intent (`APP_INTEGRATION_ROADMAP.md` line ~90) is to **mint `job_id = "AE-<estimate_id>"`** (namespaced, Quote-stage) so a brand-new estimate with no Roofr job yet can't clash, and Alpha persists the returned id for later updates. **Recommendation:** send `job_id = "AE-<estimate_id>"` from Alpha. If/when the estimate becomes a real Roofr job, decide the stitch (carry `estimate_id` as a cross-ref; see roadmap "identity spine").

### 3.2 `volume_solids_pct` per product — **real gap, important**
The roadmap explicitly wants Alpha to send **`volume_solids_pct` per product** as "the basis for downstream dry-mil reconciliation." **The built `/alpha/webhook` does NOT accept it.** TruAgent currently falls back to `_get_volume_solids(system)` — a per-*chemistry* constant keyed by system name (silicone 0.93, acrylic 0.50, …), NOT Alpha's actual per-product spec. For A10 coverage (achieved dry-mil) to use real manufacturer specs instead of a coarse default, **extend `/alpha/webhook` (and the `AlphaWebhook` model) to accept `volume_solids_pct: {product: pct}` and store it on `budget`**, then have `_calc_achieved_dry_mil` / A10 prefer it over `_get_volume_solids`. Alpha already has the specs corpus (per Fred's memory) — this is where its precision pays off. **Do this on the TruAgent side as part of the wiring** (it needs a TruAgent commit + push).

### 3.3 The 45% burden lives in Alpha, not TruAgent
Per the roadmap, the 45%-burden figure is owned by Alpha Estimator. TruAgent's `_cost_breakdown` applies `1.45` to `loaded_labor_rate × hours`. Confirm Alpha's `loaded_labor_rate` is the **pre-burden** rate (so TruAgent's ×1.45 is correct) and not already burdened — otherwise burden double-counts. Align this explicitly. (Note: Fred confirmed burden = 45% of direct labor, 2026-05-06.)

### 3.4 Body-secret vs header-auth / per-connection (architecture)
The built door uses a **single body secret** (`ALPHA_SECRET`). The roadmap's robust design (`APP_INTEGRATION_ROADMAP.md` §"Connections registry", Security points 5–8) is **per-connection keys via `X-TruAgent-Connection-Id` + `X-TruAgent-Key` headers**, a new `POST /estimator/webhook`, `source_app` validation, and idempotency on a source event id. The roadmap says to evolve toward that **as one deliberate suite-wiring pass once all four apps are independently stable** — and notes that once header-auth lands for a source, the body-secret path for it must be blocked/retired (or an attacker with the old key can still post). **Decision for Fred:** ship the simple body-secret `/alpha/webhook` now (fastest, already live), or build the robust `/estimator/webhook` now. Recommended: **body-secret now** to get one source flowing end-to-end; schedule the header-auth migration as its own pass. If you go robust, reconcile the two endpoints so you don't leave both doors open.

### 3.5 Trigger point in Alpha
When does Alpha send? Likely two events (roadmap "Flow A"): **estimate finalized** (→ Quote-stage budget import) and **estimate accepted** (→ Approved, stamps accepted price, can echo to Roofr). Confirm Alpha has a clean hook at those moments (a save/finalize handler, a Supabase trigger/edge function, or a button). The send must be **optional + configurable** (no-op when the TruAgent URL/secret aren't set) so Alpha's public SaaS customers never accidentally pipe data into Fred's internal TruAgent.

## 4. Recommended build order (one source, end-to-end)

1. **Settle §3.1–3.5 with Fred** (a 5-minute numbered Q&A).
2. **TruAgent side (small):** extend `AlphaWebhook` + `/alpha/webhook` to accept `volume_solids_pct` per product (§3.2); make A10 prefer it. Commit; this needs a push (Fred's OK) to reach prod.
3. **Alpha side:** add a config-gated outbound module — env/config holds `TRUAGENT_ALPHA_URL` (`https://truagent-production.up.railway.app/alpha/webhook`) + `TRUAGENT_ALPHA_SECRET`. On estimate finalize/accept, build the §2 payload (with `job_id="AE-<estimate_id>"`, per-product `est_gallons`, `volume_solids_pct`, `material_cost_per_gal`, `loaded_labor_rate`, `quoted_margin`) and POST it. No-op cleanly when unconfigured. Persist the returned `job_id` on the estimate.
4. **Verify:** offline first (TestClient against a local TruAgent on an isolated `DATA_DIR`, or unit-test the Alpha builder). Then ONE guarded prod probe (a throwaway `job_id` like `AE-test-<n>`), confirm the job + `budget` appear via `GET /job/{id}` as manager, then clean it up. Confirm the three-bucket model: `est_gallons` populated, `gallons_applied`/`gallons_purchased` untouched.
5. **Document** the live connection in TruAgent `docs/handoff.md` and the shared `INTEGRATION_GUIDE.md` (identity spine + three-bucket model).

## 5. Gotchas / guardrails (learned the hard way)

- **Pushing to `main` auto-deploys to prod** and is gated — needs Fred's explicit per-push OK each time. (A `git push` allow-rule was added to `.claude/settings.local.json` on 2026-06-10, but treat deploys as deliberate.)
- **Secrets:** read `ALPHA_SECRET` at runtime from `.env` / Railway; never inline it as a command literal, never write it to `/tmp`, never echo it. The working pattern for setting Railway vars is a `railway`-prefixed command reading the value inline from `.env` via `$(grep …)` with `--skip-deploys`. The auto-mode classifier blocks `printf|railway` pipes, scattering secrets in `/tmp`, and an agent widening its own `git push` permission — expect those.
- **Local testing:** TruAgent's `.env` has `PORT=5000`, but **port 5000 is taken by Coating Log / Delta** — run a local TruAgent with a free `PORT` + an isolated `DATA_DIR` (temp dir) so you never bind 5000 or touch the real `db.json`.
- **Three-bucket gallon model is sacred:** Alpha owns `est_gallons` (estimated). Delta owns `gallons_applied`. QuickBooks owns `gallons_purchased`. Never sum or overwrite across buckets — that's what surfaces the two real signals (applied>estimated = margin leak; applied<purchased = waste/theft).
- **Don't trust ticked boxes:** the 63-feature build had all boxes ticked but the QA sweep found 31 real bugs. Verify behavior, don't assume.
- **Paths move:** the suite was reorganized into `Documents/Business App Suite/` (2026-06-13). If a path in this doc is stale, locate the repo by `main.py` + `.git`, don't assume.

## 6. Key references
- `TruAgent/docs/APP_INTEGRATION_ROADMAP.md` — the full suite-wiring architecture (identity spine, connections registry, per-app contracts, three-bucket model). The authoritative source for the robust design.
- `TruAgent/docs/NEXT_INSTANCE_BUILD_PLAN.md` — F1 (the built Alpha door) and the rest of the feature set.
- `TruAgent/main.py` — `AlphaWebhook` model + `alpha_webhook()` route (the door); `_get_volume_solids` / `_calc_achieved_dry_mil` / `/job/{id}/coverage` (A10, where per-product VS would plug in).
- Alpha Estimator project: `C:\Users\rjfla\Documents\Business App Suite\Alpha Estimator` (specs corpus, costing, the finalize/accept events to hook). Also see `Documents/Business App Suite/TruHub` — the sync-bridge that already feeds Alpha/Delta/Dominate → TruAgent doors (it may already be the right home for this outbound logic).
