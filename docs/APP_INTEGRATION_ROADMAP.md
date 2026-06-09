# Sibling-App Integration Architecture — Roadmap for a Separate Future Session

> **Scope note — read this first.** This document is a **plan for a future build session**, to be run **after all four apps (TruAgent, Alpha Estimator, Delta Coating Logistics, Dominate Marketing) are independently deployed and stable.** Do **not** start building from it now. It exists so that when you're ready to wire the suite together, the identity model, security model, and per-app contracts are already decided and you (or a build agent) can execute phase-by-phase without re-litigating the architecture. Several prerequisites it depends on (persistent storage, a scheduler) are themselves separate items in the MVP gap doc and the feature catalog — get those in first.

---

## The problem in one paragraph

You have one **internal** TruAgent (Truline's ops brain) and three sibling apps that each *also* get sold publicly to other contractors. Each sibling therefore needs **two behaviors from one codebase**: (1) its normal public production behavior serving its own customers, and (2) an **optional, configurable outbound connection** that pipes data into a *specific* TruAgent — for you, your TruAgent. The danger to design out: a public customer's estimates/logs/leads leaking into your TruAgent, or your internal data leaking to a public customer. Today TruAgent authenticates **all** inbound webhooks with a **single global secret** (`ZAPIER_SECRET`) carried **in the JSON body**, and writes straight into a flat `db.json` with no notion of *which* connection sent the data. That single-secret, single-tenant, body-auth model is the thing this roadmap evolves.

---

## Recommended model: a per-connection "Connections registry"

Every TruAgent instance owns a table of **Connections**. Each sibling app treats "where do I send my operational data" as just another configurable integration target — exactly how TruAgent already treats Roofr/QuickBooks/email URLs (optional, dormant until its value is set).

**Connection row (TruAgent side):**
```
{ connection_id, source_app (alpha_estimator | delta_logistics | dominate_marketing),
  label, api_key (hashed at rest), shared_secret (hashed),
  status (active | paused), scopes, created_at }
```

**Sibling-side config block (per customer/connection):**
```
{ truagent_base_url, truagent_connection_id, truagent_api_key }
```

When those three values are filled in, the sibling POSTs its events to that TruAgent and authenticates with that connection's key. When blank, the sibling is a pure standalone product and talks to no TruAgent — **same binary, no code fork.** For your own instance the values are injected via Railway env vars so your siblings auto-wire on deploy; for everyone else they're entered through each app's own settings UI.

### Why this shape
- It mirrors a pattern your codebase already proves works (`get_openai_client()` returns `None` and the app degrades gracefully when unconfigured).
- **One inbound door per source app**, keyed and isolated, with permanent provenance.
- Cross-contamination is *structurally* impossible: a sibling knows only one TruAgent target, never holds your key unless it's your deployment, and TruAgent is a **write-only door that returns no internal data.**

---

## Public-vs-internal connection model (the resale constraint)

It is **config-driven, not a code fork.** Each sibling ships one codebase; its public behavior always runs; the TruAgent linkage is an optional outbound integration guarded by a feature flag that is simply "are the three TruAgent settings present?"

| | Your deployment (Truline) | A public customer's deployment |
|---|---|---|
| Public product behavior | Runs | Runs |
| TruAgent connection settings | Populated (via Railway env) | Blank by default |
| Emits to a TruAgent? | Yes — your TruAgent | No (unless *they* run their own TruAgent and self-configure) |
| Holds your TruAgent key? | Yes | Never |

The marketing pitch even improves: *"Alpha Estimator can feed your own ops dashboard"* becomes a sellable feature for any customer who runs their own TruAgent — same mechanism.

---

## Security model

1. **Per-connection secrets, never one shared key.** Compromising or rotating one connection never affects another. (Retires the global `ZAPIER_SECRET`.)
2. **Store only hashes** of api_key/shared_secret; show plaintext once at creation (GitHub-PAT style); compare constant-time (reuse the existing `hashlib` pattern).
3. **Secrets never in code or git.** Your connection values live in Railway env; `.env` stays gitignored. *(Prerequisite hygiene: the example secret previously flagged in `INTEGRATION_GUIDE.md` is already scrubbed to a placeholder — just confirm `.env` is gitignored and rotate the old value if it was ever a live key in git history.)*
4. **Hard tenant isolation.** Every TruAgent instance is a separate deployment with its own database — your instance and a customer's share no storage. Within an instance, every record carries `connection_id` + `source_app`, so you can always answer "where did this come from" and revoke one source without touching others.
5. **Auth material in headers** (`X-TruAgent-Connection-Id` + `X-TruAgent-Key`), not the JSON body — so it never gets logged into a job record or echoed back.
6. **Two auth conventions will coexist during the transition — design the retirement now.** Today's inbound webhooks (`/zapier/webhook`, `/quickbooks/webhook`) authenticate via a **secret in the JSON body**, and the no-code "MVP: reuse `/zapier/webhook`" path proposed below for Delta/Dominate inherits that body-secret auth. The new typed ingest endpoints use **header auth** (point 5). That's a fine bridge, but it means a window where both conventions are live. **Rule: once header-auth ingest lands for a given source, the body-secret path for that source must be blocked or retired** (reject body-secret posts, or at minimum stop documenting/advertising them). Otherwise an attacker who learns the old global `ZAPIER_SECRET` can still post jobs/logs/leads through the legacy door long after you "moved" to per-connection keys. Track the global `ZAPIER_SECRET` for explicit deprecation, not indefinite coexistence.
7. **Direction of trust:** ingest endpoints only *accept* data; they return a 200/ack and nothing more. A mis-pointed public app cannot read internal data.
8. **Validate `source_app` matches the connection** — an Alpha key cannot post a production log.
9. **Rate-limit per connection** and allow instant **Pause** from the Admin screen to cut off a noisy or breached connection.

---

## Config surface (what you actually do)

**On TruAgent:** a new **Admin → Connections** screen (Super Admin only) that lists connections, has "Add Connection" (pick source app, give it a label), generates the `connection_id` + key, shows the key once to copy, and offers Pause / Revoke / Rotate per row. This replaces today's single global "webhook URL + secret" card (`/admin/webhook-info`). For your own instance the connections can instead be seeded from Railway env vars so deploys auto-wire — env vars win, UI is the visibility/fallback layer.

**On each sibling:** a small "Connect to TruAgent" settings card (yours pre-filled from env; public customers paste their own or leave blank).

**The five-minute task for Truline:** in TruAgent Admin, click Add Connection ×3 (one per sibling), copy each key, then paste each app's key/connection-id/base-url into that app's Railway env vars. No code edits, no TruAgent redeploy.

---

## The identity spine (shared by all three siblings)

This is the most important thing to lock before any code: **one job_id reconciles the same opportunity across all four systems, and TruAgent is the reconciliation hub.**

| ID | Owner | Role |
|---|---|---|
| `job_id` | **TruAgent** (master key — the `db["jobs"]` dict key) | The spine. Everything joins on this. |
| `roofr_job_id` | Roofr | Canonical CRM id; cross-ref stored on the job. Roofr remains the single CRM of record. |
| `estimate_id` | Alpha Estimator | Immutable, never reused; cross-ref on the job. |
| `dominate_lead_id` | Dominate Marketing | Immutable lead id; the "stitch" field; cross-ref on the job. |
| `delta_log_id` | Delta (per daily log) | Idempotency key for child production-log rows. |

**Reconciliation rules:**
- A brand-new Alpha estimate has no Roofr job yet, so TruAgent **mints** `job_id = "AE-<estimate_id>"` (namespaced so it can't collide with a Roofr id) and stores it as a Quote-stage job. Alpha persists the returned `job_id` for future updates.
- A Dominate lead enters as a provisional job `job_id = "dml_<dominate_lead_id>"`; the real reconciliation happens when the lead is pushed to Roofr, Roofr assigns its id, and the inbound Roofr Zap carries `dominate_lead_id` (mapped as a Roofr custom field) so TruAgent **merges** provisional → canonical.
- Delta **never mints job identity** — it carries the Roofr `job_id` on every payload, learned via a `GET /delta/jobs` dispatch list so crews pick a job from a dropdown rather than typing ids.
- Customer identity rides denormalized (`client_name` + `address`, plus a `customer_key` = normalized email + E.164 phone for dedupe). **No separate customers table** at flat-file scale — revisit on Supabase.
- All upserts are **idempotent** on a source-side event id so Zapier re-fires and retries can't double-create.

### The three-bucket gallon model (lock this alongside the identity spine)

Gallons appear in **three** of the four systems, and they are **three different numbers that must never be summed or treated as interchangeable:**

| Bucket | Source | Stored where | Meaning |
|---|---|---|---|
| **Estimated gallons** | Alpha Estimator | `job['estimate'].estimated_gallons` | What the quote assumed (the budget). |
| **Applied gallons** | Delta daily logs | `production_logs[].gallons_applied_today` (rolled to a job total) | What the crew actually put on the roof. |
| **Purchased gallons** | QuickBooks expense lines | `financials.expenses[].gallons` | What was bought / paid for. |

The catalog's "Gallons applied vs estimated" feature uses *estimated + applied*; "purchased-vs-budgeted gallons" uses *estimated + purchased*. **No feature should ever add applied + purchased, and none should overwrite one bucket with another.** Keeping all three distinct is what lets TruAgent surface the two real signals: *applied < purchased* (waste, over-order, or theft) and *applied > estimated* (margin leak / under-quote). Carry each with its own provenance tag so a reconciliation view can show all three side by side.

---

## Per-app data flows & contracts

### A. Alpha Estimator → TruAgent (source of new opportunities)

| Flow | Direction | Mechanism | Endpoint | Key fields |
|---|---|---|---|---|
| New quoted opportunity | In | Zapier Catch Hook → POST (clone of `/zapier/webhook`), gated by own `ESTIMATOR_SECRET` | **NEW** `POST /estimator/webhook` — mints `job_id="AE-<estimate_id>"`, `source='alpha_estimator'`, `workflow_stage='Quote'`, stores spec under `job['estimate']`, returns minted id | `estimate_id`, `estimate_version`, client/customer fields, `coating_system`, `substrate`, `measured_sqft`, `estimated_gallons`, `target_dry_mils`, **`volume_solids_pct` per product** (the basis for downstream dry-mil reconciliation), est labor/material/total cost, **`loaded_labor_rate`**, **`material_cost_per_gal`**, `quoted_price`, `quoted_margin_pct`, `warranty_term`, `proposal_pdf_url` |
| Estimate accepted → real job | In | Same endpoint, `event_type='estimate_accepted'`; internally reuses existing `ROOFR_WEBHOOK_URL` push | `POST /estimator/webhook` (sets stage `Approved`, stamps `accepted_at`/`accepted_price`, pushes to Roofr carrying TruAgent's `job_id`) | `event_type`, `estimate_id`, `accepted_at`, `accepted_price`, `signed_proposal_url` |
| Estimated-vs-actual reconciliation | Out (pull) | Authed read (JWT, manager+), **not** a webhook — it returns money | **EXTEND** `GET /job/{id}/financials` to also return `job['estimate']` as an estimated-vs-actual block | `job_id` → estimate baseline joined to QuickBooks/Delta actuals |

**Estimate baseline fields** become the "estimated" side that Delta actuals and QuickBooks expenses are compared against. They live under a `job['estimate']` sub-object so they never collide with QuickBooks actuals in `financials`. **Critically, the estimate baseline is also the only place the costing multipliers live:** `loaded_labor_rate` and `material_cost_per_gal` come in here (or, failing that, from a per-job/global config) — TruAgent has no rate table of its own, and the 45%-burden figure is owned by Alpha Estimator, not TruAgent. Without these on the baseline, Delta-side projected costing (Flow B below) has no multiplier to apply.

### B. Delta Coating Logistics → TruAgent (source of production/progress/cost)

**Anchor = the Roofr `job_id`** (already TruAgent's primary key). Delta carries it on every payload and keeps `delta_log_id` as its idempotency key. Daily logs are child rows (one job, many logs).

| Flow | Direction | Mechanism | Endpoint | Key fields |
|---|---|---|---|---|
| Daily production log → progress/status | In | MVP: existing `/zapier/webhook` (no code, body-secret auth — see retirement rule in Security point 6). Robust: dedicated endpoint with header auth + own connection key, appends to `production_logs[]` keyed by `delta_log_id` | **NEW** `POST /delta/log` (or `/zapier/webhook` for the no-code proof) | `job_id` (required), `delta_log_id`, `log_date`, `sqft_completed_today/to_date`, `gallons_applied_today`, **`wet_mil_readings[]` (the crew's real-time gauge, taken during application)**, **`volume_solids_basis`** (the per-product solids % used to convert wet→expected-dry), `expected_dry_mil` (derived), `verified_dry_mil` (+min/max, when a later/destructive check is done), `labor_hours`, `crew_size`, `weather` (incl. post-application rain-free hours observed), `percent_complete` |
| Production actuals → live costing | In | Same channel; cost computed server-side, tagged `source='delta_estimated'` into a **separate** `production_costs` bucket (never into QuickBooks) | `POST /delta/log` → bucket surfaced via `GET /job/{id}/financials` split "projected (Delta)" vs "booked (QuickBooks)", manager+ only | `labor_hours × loaded_labor_rate`, `gallons_applied × material_cost_per_gal` — **both multipliers sourced from the Alpha estimate baseline (`job['estimate']`) or a config, since TruAgent holds no rate table**; plus `source`, `date` |
| Field photos & daily-report PDF | In | Reference Delta-hosted **URLs** in the log payload (preferred — Railway storage is ephemeral) or extend `/documents/upload` with optional `job_id` | Extended `POST /documents/upload` *or* `photo_urls[]` in `/delta/log` | `job_id`, `delta_log_id`, file/url, type (progress_photo / mil_reading / daily_report_pdf), caption, `taken_at` |
| Dispatch/job list (so crews log against the right job) | Out (pull) | `GET` authed by manager JWT or the connection key; operational fields only, **no money** | **NEW** `GET /delta/jobs` | `job_id`, `client_name`, `address`, `workflow_stage`, `scheduled_date` |

**Mil provenance rule (why wet-mil, not just dry-mil):** the spec-critical, warranty-defensible reading is the **wet-mil gauge taken during application** — that's the number a crew can actually record in real time. Expected dry-mil is *derived* from wet-mil via the product's volume-solids (`dry ≈ wet × volume_solids%`), and a true dry-mil is usually verified later, often destructively. So the contract carries `wet_mil_readings[]` + `volume_solids_basis` (not only an `avg_dry_mil`), which is exactly what lets the catalog's dry-mil reconciliation math be reproduced from the log instead of taking a single pre-computed dry number on faith.

**Cost provenance rule:** Delta cost = *projected/live* (`delta_estimated`); QuickBooks = *booked/authoritative* (`quickbooks_actual`). They sit in separate buckets so one never clobbers or double-counts the other. (And gallons follow the three-bucket model above — Delta owns *applied*, QuickBooks owns *purchased*, Alpha owns *estimated*.)

### C. Dominate Marketing → TruAgent (source of leads + reputation)

| Flow | Direction | Mechanism | Endpoint | Key fields |
|---|---|---|---|---|
| New inbound lead | In | Webhook POST (reuse `/zapier/webhook` normalization, body-secret auth on the no-code MVP path — retire per Security point 6 once header auth lands); own connection key on the robust path; route no-job_id records into a new `db['leads']` map keyed by `dominate_lead_id` | `POST /zapier/webhook` (with source branch) → `db['leads']` | `dominate_lead_id`, `source_app`+`source_tag`, `customer_key`, contact fields, `service_interest`, `roof_type`/`approx_sqft` if captured, and a `marketing` block (`campaign_id`, `channel`, `ad_id`, `utm_*`, `lead_cost`, `captured_at`) |
| Lead → Roofr promotion echo (merge) | In | Existing live Roofr Zaps; the inbound record carries both `job_id` and `dominate_lead_id` | `POST /zapier/webhook` (Roofr path) + a **merge step**: copy `marketing` + `customer_key` from `db['leads']` onto `db['jobs'][job_id]`, set `lead_status`, drop the provisional key | `job_id` (canonical) + `dominate_lead_id` (stitch) + `customer_key` (dedupe fallback) |
| Lead outcome / disposition feedback | Out | Outbound webhook to a Dominate Catch Hook (mirror `/roofr/update` → `DOMINATE_WEBHOOK_URL`); revenue/profit gated to authorized connections only | **NEW** `/dominate/notify` (or a branch in `update_job_status`) | `dominate_lead_id`, `job_id`, `lead_status`, won/lost flag, optional revenue/profit + `completed_at` (for ROI + review-request timing) |
| Reviews / reputation | In | Webhook POST with `record_type='review'` → separate collection (not the jobs pipeline) | `POST /zapier/webhook` → `db['reputation']` keyed by `review_id`; read-only in manager+ AI context | `review_id`, `platform`, `rating`, optional `customer_key`/`job_id` link |

**Attribution rule:** the `marketing` block is written on first ingest and **never overwritten** by later Roofr/QuickBooks updates — that's what lets TruAgent compute cost-per-lead and, once revenue/cost land, marketing ROI per campaign. **Reviews are not jobs** — they're reference signals in their own collection.

---

## Phased roadmap (for the future session)

**Phase 0 — Prerequisites & hygiene (blocking, do first).**
- Confirm `.env` stays gitignored and rotate the old `INTEGRATION_GUIDE.md` example secret if it was ever a live key (the doc itself is already scrubbed to a placeholder — this is history-hygiene, not a current leak).
- **Persistent storage must exist** — a connections registry on ephemeral `db.json` is pointless. Finish the Railway-volume / Supabase move (this is also an MVP gap-doc item). No connections work lands on ephemeral storage.
- Lock the identity spine **and the three-bucket gallon model** (above) into a shared `INTEGRATION_GUIDE.md` all four apps agree on: `job_id` master key, `estimate_id` / `roofr_job_id` / `dominate_lead_id` / `delta_log_id` cross-refs, `customer_key` dedupe rule, the estimated/applied/purchased gallon buckets and that they're never summed, that **Roofr stays the canonical CRM and `dominate_lead_id` must be mapped as a Roofr custom field**, and that **costing multipliers (`loaded_labor_rate`, `material_cost_per_gal`) ride in on the Alpha baseline or config — TruAgent owns no rate table.**

**Phase 1 — Connections registry + first source end-to-end (Alpha).**
- Add a `connections` collection; build the Admin → Connections UI (create / list / pause / rotate, reveal key once).
- Add one typed ingest route (`POST /estimator/webhook` / `/ingest/estimate`) authenticating via `X-TruAgent-Connection-Id` + `X-TruAgent-Key` against hashed secrets, validating `source_app`, stamping every record with `connection_id` + `source_app`, idempotent on a source event id.
- Begin retiring the global `ZAPIER_SECRET` **body-auth** path: once Alpha is on header auth, block body-secret posts for the Alpha source (per Security point 6).
- Wire Alpha's optional "Connect to TruAgent" outbound module (no-op when unconfigured); prove an estimate lands as a Quote-stage job with its `volume_solids_pct` and costing multipliers intact.

**Phase 2 — Add Delta + Dominate sources.**
- Reuse the same registry/auth/stamping. Delta `/ingest/production-log` (or `/delta/log`) appends gallons/wet-mil/hours/weather/photo-refs and feeds the separate `production_costs` bucket — using `loaded_labor_rate` and `material_cost_per_gal` from `job['estimate']` (or config) as the multipliers; add `GET /delta/jobs` dispatch list. Dominate `/ingest/lead` (or `/zapier/webhook` branch) creates a lead and optionally forwards to Roofr; add the Roofr-echo merge step and the `db['reputation']` branch.
- Add per-connection rate limiting + Pause. **Block the body-secret legacy door for Delta/Dominate once their header-auth endpoints are live.** Seed Truline's three connections from Railway env vars so deploys auto-wire.

**Phase 3 — Closed-loop, sellable & hardened.**
- Extend `GET /job/{id}/financials` to show estimated (Alpha) vs projected (Delta) vs booked (QuickBooks); teach the manager+ AI prompt that `job['estimate']` and production data exist.
- Add the Dominate outbound notify (lead outcome + `job_completed` to time review requests), revenue gated.
- Expose the "Connect to TruAgent" card to public customers in each sibling; add a per-connection delivery log / "last received" indicator + alerting on repeated auth failures; document key rotation. **Formally deprecate and remove the global `ZAPIER_SECRET` body-auth path entirely** now that every source is on per-connection header auth. Optionally replace Zapier transport with direct signed POSTs.

**Phase 4 — Graduate off the flat file (when scale demands).**
- Migrate jobs/leads/reputation/production_logs to shared **Supabase Postgres** (the stack the siblings already use), with a `jobs` table keyed by `job_id`, a `production_logs` child table (carrying `wet_mil_readings`, `volume_solids_basis`, `gallons_applied`), and an `opportunities` table carrying `estimate_id` / `roofr_id` / `job_id` / `customer_key` as columns with DB-level uniqueness. Cross-app reconciliation becomes a foreign-key join instead of a webhook stitch, eliminating the merge-race. Reserve Zapier for true third-party hops (Roofr, QuickBooks), not app-to-app sync.

---

## One-line summary for each sibling

- **Alpha Estimator** → mints `AE-<estimate_id>` jobs in the Quote stage, carries `volume_solids_pct` + the loaded-labor-rate / material-$/gal multipliers, then flips to Approved + pushes to Roofr on acceptance. The estimate baseline is the yardstick for all downstream variance and the only source of costing multipliers (TruAgent owns no rate table).
- **Delta Coating Logistics** → carries the Roofr `job_id` on every daily log (learned via `GET /delta/jobs`); reports **wet-mil readings + solids basis** (so dry-mil reconciliation is reproducible) and *applied* gallons; feeds progress + *projected* costs into a bucket separate from QuickBooks.
- **Dominate Marketing** → lands leads in a `db['leads']` store, stitches to the canonical job via `dominate_lead_id` on the Roofr echo, preserves campaign attribution forever, gets closed-loop outcome + review-timing signals back.